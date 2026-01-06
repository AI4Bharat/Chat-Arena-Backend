import io
import logging
from google.cloud import storage
from django.conf import settings
import pandas as pd
import json

# Try importing parsing libraries with graceful fallbacks
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

logger = logging.getLogger(__name__)

def get_file_content(file_path):
    """Download file content from GCS."""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(settings.GS_BUCKET_NAME)
        blob = bucket.blob(file_path)
        content = blob.download_as_bytes()
        return content
    except Exception as e:
        logger.error(f"Error downloading file from GCS: {e}")
        return None

def extract_text_from_document(file_path):
    """Extract text from document based on file extension."""
    if not file_path:
        return None
        
    content = get_file_content(file_path)
    if not content:
        return "[Error: Could not retrieve document content]"

    file_ext = file_path.lower().split('.')[-1]
    file_stream = io.BytesIO(content)

    text = ""
    try:
        if file_ext == 'pdf':
            if PdfReader:
                reader = PdfReader(file_stream)
                for page in reader.pages:
                    extract = page.extract_text()
                    if extract:
                        text += extract + "\n"
            else:
                return "[System Message: To extract text from PDFs, please install the 'pypdf' library in your backend environment: pip install pypdf]"

        elif file_ext in ['docx', 'doc']:
            if DocxDocument:
                doc = DocxDocument(file_stream)
                for para in doc.paragraphs:
                    text += para.text + "\n"
            else:
                 return "[System Message: To extract text from Word documents, please install the 'python-docx' library in your backend environment: pip install python-docx]"

        elif file_ext in ['xlsx', 'xls', 'csv']:
             try:
                 if file_ext == 'csv':
                     df = pd.read_csv(file_stream)
                 else:
                     df = pd.read_excel(file_stream)
                 # Convert full dataframe to string representation
                 text = df.to_string(index=False)
             except Exception as e:
                 return f"[Error parsing spreadsheet: {str(e)}]"

        elif file_ext in ['txt', 'md', 'py', 'js', 'json', 'html', 'css', 'rtf', 'xml', 'yaml', 'yml']:
            # Try utf-8 decoding
            text = content.decode('utf-8', errors='ignore')

        else:
            text = f"[System Message: File type '.{file_ext}' is not currently supported for text extraction]"

    except Exception as e:
        logger.error(f"Error extracting text: {e}")
        text = f"[Error extracting text from document: {str(e)}]"

    return text
