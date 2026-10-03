# Terraform configuration for ATLAS on Azure

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.80"
    }
  }
}

provider "azurerm" {
  features {
    virtual_machine {
      delete_os_disk_on_deletion            = true
      graceful_shutdown                     = false
      skip_shutdown_and_force_delete        = false
    }
  }
  
  skip_provider_registration = false
}

variable "location" {
  default = "eastus"
}

variable "environment" {
  default = "dev"
}

variable "resource_group_name" {
  default = "atlas-rg"
}

# Resource Group
resource "azurerm_resource_group" "atlas" {
  name     = "${var.resource_group_name}-${var.environment}"
  location = var.location
}

# PostgreSQL
resource "azurerm_postgresql_flexible_server" "atlas" {
  name                   = "atlas-postgres-${var.environment}"
  location               = azurerm_resource_group.atlas.location
  resource_group_name    = azurerm_resource_group.atlas.name
  
  administrator_login    = "atlasadmin"
  administrator_password = random_password.postgres_password.result
  
  sku_name   = "B_Standard_B2s"
  storage_mb = 32768
  version    = "16"
  
  backup_retention_days        = 7
  geo_redundant_backup_enabled = false
  
  # TODO: Add proper network configuration
}

# Redis
resource "azurerm_redis_cache" "atlas" {
  name                = "atlas-redis-${var.environment}"
  location            = azurerm_resource_group.atlas.location
  resource_group_name = azurerm_resource_group.atlas.name
  
  capacity            = 0
  family              = "C"
  sku_name            = "Basic"
  
  enable_non_ssl_port = false
  minimum_tls_version = "1.2"
}

# Storage Account (for MinIO-like functionality)
resource "azurerm_storage_account" "atlas" {
  name                     = "atlas${var.environment}sa"
  location                 = azurerm_resource_group.atlas.location
  resource_group_name      = azurerm_resource_group.atlas.name
  account_tier             = "Standard"
  account_replication_type = "GRS"
  
  https_traffic_only_enabled = true
  min_tls_version            = "TLS1_2"
}

# AKS Cluster
resource "azurerm_kubernetes_cluster" "atlas" {
  name                = "atlas-aks-${var.environment}"
  location            = azurerm_resource_group.atlas.location
  resource_group_name = azurerm_resource_group.atlas.name
  
  dns_prefix = "atlas-${var.environment}"
  
  default_node_pool {
    name       = "default"
    node_count = 3
    vm_size    = "Standard_D2s_v3"
    
    os_sku           = "Ubuntu"
    os_disk_size_gb  = 30
  }
  
  identity {
    type = "SystemAssigned"
  }
  
  network_profile {
    network_plugin = "azure"
  }
}

# Random password for PostgreSQL
resource "random_password" "postgres_password" {
  length  = 32
  special = true
}

# Outputs
output "postgres_host" {
  value = azurerm_postgresql_flexible_server.atlas.fqdn
}

output "redis_host" {
  value = azurerm_redis_cache.atlas.hostname
}

output "storage_account" {
  value = azurerm_storage_account.atlas.name
}

output "aks_cluster_name" {
  value = azurerm_kubernetes_cluster.atlas.name
}
