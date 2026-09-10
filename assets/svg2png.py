from pathlib import Path
import fitz  # PyMuPDF

# Folder containing your generated SVGs
input_dir = Path("individual_figures")

# Process every SVG in the folder
for svg_path in input_dir.glob("*.svg"):
    png_path = svg_path.with_suffix(".png")

    try:
        # Load the SVG as a document
        doc = fitz.open(str(svg_path))
        page = doc[0]

        # DPI=150 gives sharp resolution (increase to 300 if you want higher resolution)
        pix = page.get_pixmap(dpi=150)
        pix.save(str(png_path))

        print(f"Successfully converted: {svg_path.name} -> {png_path.name}")
    except Exception as e:
        print(f"Error converting {svg_path.name}: {e}")