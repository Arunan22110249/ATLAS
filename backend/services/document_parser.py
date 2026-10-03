"""
Document parsing utilities.
"""

import hashlib
import re


class DocumentParser:
    """Base class for document parsing."""
    
    @staticmethod
    def parse_pdf(file_path: str) -> str:
        """Parse PDF document."""
        try:
            import pdfplumber
            text_content = []
            
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if text:
                        text_content.append(f"[Page {page_num + 1}]\n{text}")
            
            return "\n\n".join(text_content)
        except Exception as e:
            raise ValueError(f"Failed to parse PDF: {e!s}")
    
    @staticmethod
    def parse_docx(file_path: str) -> str:
        """Parse DOCX document."""
        try:
            from docx import Document
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)
        except Exception as e:
            raise ValueError(f"Failed to parse DOCX: {e!s}")
    
    @staticmethod
    def parse_txt(file_path: str) -> str:
        """Parse TXT document."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            raise ValueError(f"Failed to parse TXT: {e!s}")
    
    @staticmethod
    def parse_markdown(file_path: str) -> str:
        """Parse Markdown document."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            raise ValueError(f"Failed to parse Markdown: {e!s}")
    
    @staticmethod
    def parse_html(file_path: str) -> str:
        """Parse HTML document."""
        try:
            from html.parser import HTMLParser
            
            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text_parts = []
                    self.skip_content = False
                
                def handle_starttag(self, tag, attrs):
                    if tag in ['script', 'style']:
                        self.skip_content = True
                
                def handle_endtag(self, tag):
                    if tag in ['script', 'style']:
                        self.skip_content = False
                
                def handle_data(self, data):
                    if not self.skip_content and data.strip():
                        self.text_parts.append(data.strip())
            
            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            parser = TextExtractor()
            parser.feed(html_content)
            return "\n".join(parser.text_parts)
        except Exception as e:
            raise ValueError(f"Failed to parse HTML: {e!s}")
    
    @staticmethod
    def parse_csv(file_path: str) -> str:
        """Parse CSV document."""
        try:
            import csv
            rows = []
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    rows.append(" | ".join(row))
            return "\n".join(rows)
        except Exception as e:
            raise ValueError(f"Failed to parse CSV: {e!s}")
    
    @staticmethod
    def parse_json(file_path: str) -> str:
        """Parse JSON document."""
        try:
            import json
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return json.dumps(data, indent=2)
        except Exception as e:
            raise ValueError(f"Failed to parse JSON: {e!s}")
    
    @classmethod
    def parse(cls, file_path: str, mime_type: str) -> str:
        """Parse document based on MIME type."""
        mime_to_parser = {
            'application/pdf': cls.parse_pdf,
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': cls.parse_docx,
            'text/plain': cls.parse_txt,
            'text/markdown': cls.parse_markdown,
            'text/html': cls.parse_html,
            'text/csv': cls.parse_csv,
            'application/json': cls.parse_json,
        }
        
        parser = mime_to_parser.get(mime_type)
        if not parser:
            raise ValueError(f"Unsupported MIME type: {mime_type}")
        
        return parser(file_path)


class TextCleaner:
    """Clean and normalize text content."""
    
    @staticmethod
    def clean(text: str) -> str:
        """Clean text content."""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove special characters but keep basic punctuation
        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', text)
        return text.strip()
    
    @staticmethod
    def normalize(text: str) -> str:
        """Normalize text for processing."""
        text = text.lower()
        text = re.sub(r'\s+', ' ', text)
        return text.strip()


class TextChunker:
    """Split text into chunks."""
    
    @staticmethod
    def chunk_by_size(
        text: str,
        chunk_size: int = 512,
        overlap: int = 100
    ) -> list[str]:
        """Chunk text by size with overlap."""
        chunks = []
        words = text.split()
        
        current_chunk = []
        for word in words:
            current_chunk.append(word)
            chunk_text = " ".join(current_chunk)
            
            if len(chunk_text) >= chunk_size:
                chunks.append(chunk_text)
                # Keep last N words for overlap
                current_chunk = current_chunk[-(overlap // 5):]
        
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return [c.strip() for c in chunks if c.strip()]
    
    @staticmethod
    def chunk_by_sentences(
        text: str,
        max_sentences: int = 5
    ) -> list[str]:
        """Chunk text by sentences."""
        # Simple sentence splitting
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current_chunk = []
        
        for sentence in sentences:
            current_chunk.append(sentence)
            if len(current_chunk) >= max_sentences:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
        
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks
    
    @staticmethod
    def chunk_by_paragraphs(text: str) -> list[str]:
        """Chunk text by paragraphs."""
        paragraphs = text.split('\n\n')
        return [p.strip() for p in paragraphs if p.strip()]


class ContentDeduplicator:
    """Detect and handle duplicate content."""
    
    @staticmethod
    def calculate_checksum(content: str) -> str:
        """Calculate SHA256 checksum of content."""
        return hashlib.sha256(content.encode()).hexdigest()
    
    @staticmethod
    def calculate_content_hash(text: str) -> str:
        """Calculate hash of normalized content."""
        normalized = re.sub(r'\s+', ' ', text.lower()).strip()
        return hashlib.md5(normalized.encode()).hexdigest()
    
    @staticmethod
    def similarity_ratio(text1: str, text2: str) -> float:
        """Calculate similarity ratio between two texts (0-1)."""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, text1, text2).ratio()
    
    @staticmethod
    def is_duplicate(
        text1: str,
        text2: str,
        threshold: float = 0.95
    ) -> bool:
        """Check if two texts are duplicates."""
        ratio = ContentDeduplicator.similarity_ratio(text1, text2)
        return ratio >= threshold
