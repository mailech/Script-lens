import fitz  # PyMuPDF
import os
import uuid


def extract_images_from_pdf(pdf_path: str, output_dir: str) -> list:
    """
    Extracts pages from a PDF as high-resolution images.
    Strategy: ALWAYS render each page as an image (2x zoom = 144 DPI),
    so "1 page = 1 image" is guaranteed for all PDF types
    (scanned, photographed, or embedded-image PDFs).
    """
    doc = fitz.open(pdf_path)
    extracted_images = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)

        # Render at 2x zoom for crisp quality (144 DPI)
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        image_id = str(uuid.uuid4())
        filename = f"scene_{page_num + 1:03d}_{image_id}.png"
        filepath = os.path.join(output_dir, filename)

        pix.save(filepath)

        extracted_images.append({
            "image_id": image_id,
            "page_number": page_num + 1,
            "image_index": 0,
            "filepath": filepath,
            "filename": filename,
        })

    doc.close()
    return extracted_images
