"""
AI-powered PDF parser for SENS announcements.
Multi-stage parsing: OCR → AI fallback → Summary generation.
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime

import pytesseract
import pdf2image
from PIL import Image
from openai import OpenAI
import anthropic

from ..utils.config import get_config
from ..database.models import SensAnnouncement

logger = logging.getLogger(__name__)


class PDFParseError(Exception):
    """Custom exception for PDF parsing errors."""
    pass


class PDFParser:
    """Multi-stage PDF parser with OCR and AI fallback."""
    
    def __init__(self):
        self.config = get_config()
        self._setup_ai_clients()
    
    def _setup_ai_clients(self):
        """Initialize AI API clients based on configuration."""
        # PDF Parsing clients
        parse_openai_key = self.config.get_pdf_parse_openai_key()
        if self.config.pdf_parse_provider == "openai" and parse_openai_key:
            self.parse_openai_client = OpenAI(api_key=parse_openai_key)
        else:
            self.parse_openai_client = None
            
        parse_anthropic_key = self.config.get_pdf_parse_anthropic_key()
        if self.config.pdf_parse_provider == "anthropic" and parse_anthropic_key:
            self.parse_anthropic_client = anthropic.Anthropic(api_key=parse_anthropic_key)
        else:
            self.parse_anthropic_client = None
            
        # Summary Generation clients
        summary_openai_key = self.config.get_summary_openai_key()
        if self.config.summary_provider == "openai" and summary_openai_key:
            self.summary_openai_client = OpenAI(api_key=summary_openai_key)
        else:
            self.summary_openai_client = None
            
        summary_anthropic_key = self.config.get_summary_anthropic_key()
        if self.config.summary_provider == "anthropic" and summary_anthropic_key:
            self.summary_anthropic_client = anthropic.Anthropic(api_key=summary_anthropic_key)
        else:
            self.summary_anthropic_client = None
    
    def parse_sens_pdf(self, announcement: SensAnnouncement) -> SensAnnouncement:
        """
        Parse a SENS PDF with multi-stage approach.
        
        Args:
            announcement: SensAnnouncement object with local_pdf_path
            
        Returns:
            Updated SensAnnouncement with parsed content and summary
        """
        if not announcement.local_pdf_path or not os.path.exists(announcement.local_pdf_path):
            logger.error(f"PDF file not found: {announcement.local_pdf_path}")
            announcement.parse_status = "failed"
            announcement.parse_method = "no_file"
            return announcement
        
        logger.info(f"Starting PDF parsing for SENS {announcement.sens_number}")
        announcement.parse_status = "processing"
        announcement.parsed_at = datetime.now()
        
        try:
            # Stage 1: Try OCR first (fast and cheap)
            content, ocr_quality = self._extract_with_ocr(announcement.local_pdf_path)
            
            if ocr_quality == "good":
                logger.info(f"OCR successful for SENS {announcement.sens_number}")
                announcement.pdf_content = content
                announcement.parse_method = "ocr"
            else:
                logger.warning(f"OCR quality poor for SENS {announcement.sens_number}, trying AI")
                # Stage 2: Fallback to AI parsing
                content = self._extract_with_ai(announcement.local_pdf_path, content)
                announcement.pdf_content = content
                announcement.parse_method = "ai"
            
            # Stage 3: Generate AI summary
            if content:
                summary = self._generate_summary(content, announcement)
                announcement.ai_summary = summary
                announcement.parse_status = "completed"
                logger.info(f"Successfully parsed and summarized SENS {announcement.sens_number}")
            else:
                announcement.parse_status = "failed"
                logger.error(f"No content extracted from SENS {announcement.sens_number}")
                
        except Exception as e:
            logger.error(f"PDF parsing failed for SENS {announcement.sens_number}: {e}")
            announcement.parse_status = "failed"
            announcement.parse_method = "error"
        
        return announcement
    
    def _extract_with_ocr(self, pdf_path: str) -> Tuple[str, str]:
        """
        Extract text using OCR and assess quality.
        
        Returns:
            Tuple of (extracted_text, quality_assessment)
            quality_assessment: 'good', 'poor'
        """
        try:
            logger.debug(f"Converting PDF to images: {pdf_path}")
            
            # Resolve poppler path (prefer explicit env POPPLER_PATH, then common locations)
            poppler_path = os.environ.get('POPPLER_PATH')
            if not poppler_path:
                conda_bin = Path("C:/PythonEnvironments/debbi/Library/bin")
                if conda_bin.exists():
                    poppler_path = str(conda_bin)
                    logger.debug(f"Using conda poppler path: {poppler_path}")
            
            # Resolve tesseract executable if present
            tesseract_cmd_env = os.environ.get('TESSERACT_CMD')
            if tesseract_cmd_env and Path(tesseract_cmd_env).exists():
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd_env
            else:
                # Try common locations (Windows conda env first)
                candidates: List[Path] = []
                if 'conda_bin' in locals():
                    candidates.append(conda_bin / 'tesseract.exe')
                candidates.extend([
                    Path('C:/Program Files/Tesseract-OCR/tesseract.exe'),
                    Path('/usr/bin/tesseract'),
                    Path('/usr/local/bin/tesseract'),
                ])
                for cand in candidates:
                    if cand.exists():
                        pytesseract.pytesseract.tesseract_cmd = str(cand)
                        logger.debug(f"Using tesseract path: {cand}")
                        break
            
            # Resolve tessdata directory (must contain eng.traineddata)
            tessdata_env = os.environ.get('TESSDATA_PREFIX')
            def _has_eng(p: Path) -> bool:
                return (p / 'eng.traineddata').exists()
            tess_candidates: List[Path] = []
            if tessdata_env:
                tess_candidates.append(Path(tessdata_env))
            if 'conda_bin' in locals():
                tess_candidates.extend([
                    conda_bin.parent / 'share' / 'tessdata',
                    conda_bin.parent / 'tessdata',
                ])
            tess_candidates.extend([
                Path('C:/Program Files/Tesseract-OCR/tessdata'),
                Path('/usr/share/tesseract-ocr/4.00/tessdata'),
                Path('/usr/share/tesseract-ocr/tessdata'),
                Path('/usr/share/tessdata'),
                Path('/usr/local/share/tessdata'),
            ])
            for tdir in tess_candidates:
                if tdir.exists() and _has_eng(tdir):
                    os.environ['TESSDATA_PREFIX'] = str(tdir)
                    logger.debug(f"Using tessdata path: {tdir}")
                    break
            
            # Convert PDF to images
            pages = pdf2image.convert_from_path(
                pdf_path, 
                dpi=300, 
                poppler_path=poppler_path
            )
            
            all_text = []
            total_chars = 0
            
            for i, page in enumerate(pages):
                logger.debug(f"OCR processing page {i+1}/{len(pages)}")
                # Extract text from each page
                text = pytesseract.image_to_string(page, config='--psm 6')
                all_text.append(text)
                total_chars += len(text.strip())
            
            full_text = "\\n\\n".join(all_text)
            
            # Assess OCR quality
            quality = self._assess_ocr_quality(full_text, total_chars)
            
            logger.debug(f"OCR extracted {total_chars} characters, quality: {quality}")
            return full_text, quality
            
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return "", "poor"
    
    def _assess_ocr_quality(self, text: str, char_count: int) -> str:
        """
        Assess OCR quality to decide if AI fallback is needed.
        
        Args:
            text: Extracted text
            char_count: Total character count
            
        Returns:
            'good' or 'poor'
        """
        if char_count < 100:
            return "poor"  # Too little text extracted
        
        # Check for OCR artifacts that indicate poor quality
        artifacts = [
            r'[^\w\s\.,;:!?\-\(\)%\$£€]',  # Unusual characters
            r'\b[a-zA-Z]{1}\s[a-zA-Z]{1}\s',  # Single letters with spaces (broken words)
            r'\d{5,}',  # Long number sequences (often OCR errors)
        ]
        
        artifact_count = 0
        for pattern in artifacts:
            matches = re.findall(pattern, text)
            artifact_count += len(matches)
        
        # If more than 10% of characters are artifacts, quality is poor
        if artifact_count > (char_count * 0.1):
            return "poor"
        
        # Check for reasonable word structure
        words = text.split()
        if len(words) < 20:
            return "poor"  # Too few words
            
        # Check average word length (OCR errors often create very short or very long "words")
        avg_word_length = sum(len(word) for word in words) / len(words)
        if avg_word_length < 2 or avg_word_length > 15:
            return "poor"
        
        return "good"
    
    def _extract_with_pypdf(self, pdf_path: str) -> str:
        """
        Extract text using PyPDF2 and pdfplumber as fallback.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Extracted text or empty string if failed
        """
        try:
            # Try pdfplumber first (better text extraction)
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                
                if text.strip():
                    logger.debug(f"pdfplumber extracted {len(text)} characters")
                    return text.strip()
        except Exception as e:
            logger.debug(f"pdfplumber failed: {e}")
        
        try:
            # Fallback to PyPDF2
            import PyPDF2
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                
                if text.strip():
                    logger.debug(f"PyPDF2 extracted {len(text)} characters")
                    return text.strip()
        except Exception as e:
            logger.debug(f"PyPDF2 failed: {e}")
        
        return ""
    
    def _extract_with_ai(self, pdf_path: str, ocr_text: str) -> str:
        """
        Extract and clean text using AI when OCR fails.
        
        Args:
            pdf_path: Path to PDF file
            ocr_text: Raw OCR text (may be poor quality)
            
        Returns:
            Cleaned and structured text
        """
        if not self._parse_ai_available():
            logger.error("No AI client available for PDF parsing")
            return ocr_text  # Return OCR text as fallback
        
        try:
            # If OCR failed completely, extract text using PyPDF2/pdfplumber first
            if not ocr_text or len(ocr_text.strip()) < 50:
                logger.info("OCR failed, extracting text with PyPDF2/pdfplumber for AI processing")
                extracted_text = self._extract_with_pypdf(pdf_path)
                if extracted_text:
                    ocr_text = extracted_text
                    logger.info(f"Extracted {len(extracted_text)} characters with PyPDF2/pdfplumber")
                else:
                    logger.warning("Both OCR and PyPDF2/pdfplumber failed to extract text")
                    return ""
            
            prompt = self._create_parsing_prompt(ocr_text)
            
            if self.config.pdf_parse_provider == "openai":
                response = self.parse_openai_client.chat.completions.create(
                    model=self.config.pdf_parse_openai_model,
                    messages=[
                        {"role": "system", "content": "You are a financial document parser specializing in JSE SENS announcements."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=2000,
                    temperature=0.1
                )
                return response.choices[0].message.content.strip()
                
            elif self.config.pdf_parse_provider == "anthropic":
                response = self.parse_anthropic_client.messages.create(
                    model=self.config.pdf_parse_anthropic_model,
                    max_tokens=2000,
                    temperature=0.1,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.content[0].text.strip()
                
        except Exception as e:
            logger.error(f"AI parsing failed: {e}")
            return ocr_text  # Fallback to OCR text
    
    def _create_parsing_prompt(self, ocr_text: str) -> str:
        """Create prompt for AI-based text cleaning and parsing."""
        return f"""
Please clean and structure the following OCR-extracted text from a JSE SENS announcement. 
The OCR may have errors, broken words, or formatting issues.

Your task:
1. Fix obvious OCR errors and broken words
2. Structure the content logically
3. Preserve all financial data, dates, and company information
4. Remove excessive whitespace and formatting artifacts
5. Return clean, readable text that maintains the original meaning. Do NOT add assumptions. Do NOT insert phrases like "details not provided" unless those exact words appear.

OCR Text:
{ocr_text}

Please return only the cleaned text without any explanations or comments.
"""
    
    def _generate_summary(self, content: str, announcement: SensAnnouncement) -> str:
        """
        Generate concise AI summary of the SENS announcement.
        
        Args:
            content: Parsed PDF content
            announcement: SENS announcement object
            
        Returns:
            Concise summary (max 50 words)
        """
        if not self._summary_ai_available():
            logger.error("No AI client available for summary generation")
            return ""
        
        try:
            prompt = self._create_summary_prompt(content, announcement)
            
            if self.config.summary_provider == "openai":
                response = self.summary_openai_client.chat.completions.create(
                    model=self.config.summary_openai_model,
                    messages=[
                        {"role": "system", "content": "You are a financial analyst creating concise summaries of JSE SENS announcements."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=250,
                    temperature=0.1
                )
                return response.choices[0].message.content.strip()
                
            elif self.config.summary_provider == "anthropic":
                response = self.summary_anthropic_client.messages.create(
                    model=self.config.summary_anthropic_model,
                    max_tokens=250,
                    temperature=0.1,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.content[0].text.strip()
                
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return ""
    
    def _create_summary_prompt(self, content: str, announcement: SensAnnouncement) -> str:
        """Create prompt for AI summary generation."""
        cleaned = content[:10000]
        return f"""
Summarize the announcement in <= {self.config.summary_max_words} words. No preamble. No company name restatement. Focus ONLY on substance:
- instrument/security, amounts/percentages, prices, key dates, tickers/codes, parties, and effects on holders
- if it's an interest or listing notice, extract the essential fields above
- do NOT use vague phrases like "further details were not provided" unless the text explicitly says so

Title: {announcement.title}
SENS: {announcement.sens_number}

Text:
{cleaned}
"""
    
    def _parse_ai_available(self) -> bool:
        """Check if AI client is available for PDF parsing."""
        if self.config.pdf_parse_provider == "openai":
            return self.parse_openai_client is not None and self.config.get_pdf_parse_openai_key()
        elif self.config.pdf_parse_provider == "anthropic":
            return self.parse_anthropic_client is not None and self.config.get_pdf_parse_anthropic_key()
        return False
    
    def _summary_ai_available(self) -> bool:
        """Check if AI client is available for summary generation."""
        if self.config.summary_provider == "openai":
            return self.summary_openai_client is not None and self.config.get_summary_openai_key()
        elif self.config.summary_provider == "anthropic":
            return self.summary_anthropic_client is not None and self.config.get_summary_anthropic_key()
        return False


def parse_sens_announcement(announcement: SensAnnouncement) -> SensAnnouncement:
    """
    Convenience function to parse a single SENS announcement.
    
    Args:
        announcement: SensAnnouncement object
        
    Returns:
        Updated announcement with parsed content and summary
    """
    parser = PDFParser()
    return parser.parse_sens_pdf(announcement)
