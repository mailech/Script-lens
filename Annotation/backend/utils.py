import fitz  # PyMuPDF
import io
import os
import uuid

def extract_images_from_pdf(pdf_path, output_dir):
    """
    Extracts images from a PDF. 
    Handles both embedded images AND full-page images (scanned PDFs).
    Uses ONLY PyMuPDF to avoid Poppler dependency.
    """
    doc = fitz.open(pdf_path)
    extracted_images = []

    # First attempt: Extract embedded images
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        image_list = page.get_images(full=True)

        for img_index, img in enumerate(image_list):
            try:
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Generate local filename
                image_id = str(uuid.uuid4())
                filename = f"img_{image_id}.{image_ext}"
                filepath = os.path.join(output_dir, filename)
                
                with open(filepath, "wb") as f:
                    f.write(image_bytes)
                
                extracted_images.append({
                    "image_id": image_id,
                    "page_number": page_num + 1,
                    "image_index": img_index,
                    "filepath": filepath,
                    "filename": filename
                })
            except Exception as e:
                print(f"Failed to extract image {img_index} on page {page_num}: {e}")

    # Fallback/Supplemental: If no embedded images found OR if we want to treat each page as an image
    # (Scanned PDFs often have ONE embedded image per page, but sometimes it's just a page render)
    if not extracted_images:
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) # Zoom for better quality
            
            image_id = str(uuid.uuid4())
            filename = f"page_{page_num+1}_{image_id}.png"
            filepath = os.path.join(output_dir, filename)
            pix.save(filepath)
            
            extracted_images.append({
                "image_id": image_id,
                "page_number": page_num + 1,
                "image_index": 0,
                "filepath": filepath,
                "filename": filename
            })

    return extracted_images
