import fitz
import sys
import os

def debug_pdf(path):
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return
    
    doc = fitz.open(path)
    text = ""
    print(f"Total Pages: {len(doc)}")
    # Get first 3 pages
    for i in range(min(3, len(doc))):
        text += f"--- PAGE {i+1} ---\n"
        text += doc[i].get_text("text")
    
    print("--- TEXT DUMP (First 3 Pages) ---")
    print(text)
    doc.close()

if __name__ == "__main__":
    # Look for the pdf in the current dir or subdirs
    # The user mentioned "LITTLE HEARTS -Screenplay by Sai Marthand.pdf"
    # But I don't have the path. I'll search for it.
    pass
