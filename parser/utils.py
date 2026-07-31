import logging
import os
import shutil
from git import Repo

logger = logging.getLogger(__name__)

def clone_repository(repo_url: str, dest_path: str, branch: str = "main"):
    """
    Clones a repository with depth=1 to save space and time.
    """
    if os.path.exists(dest_path):
        shutil.rmtree(dest_path)
    
    Repo.clone_from(repo_url, dest_path, depth=1, branch=branch)
    return dest_path

def clone_repository_sparse(repo_url: str, dest_path: str, branch: str, 
                             sparse_paths: list[str] = None):
    """
    Klont mit sparse-checkout — lädt nur relevante Verzeichnisse.
    Reduziert 100-GB-Repo auf z. B. 10 GB wenn nur ein Unterordner relevant ist.
    """
    import subprocess
    if os.path.exists(dest_path):
        shutil.rmtree(dest_path)
    os.makedirs(dest_path, exist_ok=True)
    subprocess.run(["git", "init", dest_path], check=True)
    subprocess.run(["git", "-C", dest_path, "remote", "add", "origin", repo_url], check=True)
    subprocess.run(["git", "-C", dest_path, "config", "core.sparseCheckout", "true"], check=True)
    
    if sparse_paths:
        sparse_file = os.path.join(dest_path, ".git", "info", "sparse-checkout")
        with open(sparse_file, "w") as f:
            f.write("\n".join(sparse_paths) + "\n")
    
    subprocess.run([
        "git", "-C", dest_path, "fetch", "--depth=1", "origin", branch
    ], check=True)
    subprocess.run([
        "git", "-C", dest_path, "checkout", branch
    ], check=True)
    return dest_path

EXCLUDE_DIRS = {
    "node_modules", ".git", ".svn", ".hg",
    "vendor", "dist", "build", "target",      # Build-Outputs
    "__pycache__", ".pytest_cache", ".mypy_cache",
    "coverage", ".coverage", ".nyc_output",
    ".terraform", ".gradle", ".m2",
    "venv", ".venv", "env", ".env",
    "bower_components", ".cache",
}

MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB pro Datei

def list_files_iter(repo_path: str, extensions=None):
    """Generator statt Liste — gibt Pfade lazy zurück, kein RAM-Anstieg."""
    if extensions is None:
        extensions = { ".py", ".js", ".jsx",
                       ".ts", ".tsx", ".cpp", ".h", ".hpp", ".c", ".cc",
                       ".java", ".go", ".rs", ".cs", ".sh", ".md",
                       ".html", ".css", ".sql", ".xml", ".yaml", ".yml" }
    for root, dirs, files in os.walk(repo_path):
        # In-place filtern damit os.walk nicht in excluded dirs absteigt
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext not in extensions:
                continue
            full_path = os.path.join(root, file)
            try:
                if os.path.getsize(full_path) <= MAX_FILE_SIZE_BYTES:
                    yield full_path
            except OSError:
                continue

def list_files(repo_path: str, extensions=None):
    """
    Lists all files in the repository with specific extensions.
    Deprecated: use list_files_iter instead for better memory efficiency.
    """
    return list(list_files_iter(repo_path, extensions))

def extract_text_from_pdf_ocr(pdf_path: str) -> str:
    """
    Extracts text from a rasterized PDF using pdf2image and pytesseract.
    Returns the concatenated OCR text.
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        return ""
        
    try:
        # Convert PDF pages to images
        images = convert_from_path(pdf_path)
        text = ""
        for image in images:
            # lang='deu+eng' requires tesseract-ocr-deu to be installed
            text += pytesseract.image_to_string(image, lang='deu+eng') + "\n"
        return text
    except Exception as e:
        logger.error(f"OCR failed for {pdf_path}: {e}")
        return ""
