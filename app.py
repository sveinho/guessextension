import io
import os
import re
import zipfile
from flask import Flask, flash, redirect, render_template, request, send_file

app = Flask(__name__)
app.secret_key = "super_secret_key_for_testing"

# Limit file uploads to 16 MB
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def guess_extended_extension(file_bytes):
    """Analyzes file content and guesses between 15 text and raw formats."""
    try:
        # Decode the first 5000 characters as text for a thorough pattern analysis
        start_text = file_bytes[:5000].decode("utf-8", errors="ignore")
        clean_text = start_text.strip()
    except Exception:
        # If it cannot be decoded at all, it is likely unstructured binary/raw data
        return ".bin"

    if not clean_text:
        return ".txt"

    # --- 1. CHECK STRUCTURED DATA AND WEB FORMATS ---
    if clean_text.startswith("{") or clean_text.startswith("["):
        return ".json"

    if clean_text.startswith("<"):
        if "html" in clean_text.lower() or "<body" in clean_text.lower():
            return ".html"
        return ".xml"

    # CSS (Frequent use of classes/IDs and curly braces: .class { } or #id { })
    if re.search(r"[\.#\w-]+\s*\{\s*[\w-]+\s*:", clean_text):
        return ".css"

    # Markdown (Often starts with # Heading, [Link](url) or **bold**)
    if clean_text.startswith("# ") or re.search(r"\[.+\]\(.+\)", clean_text):
        return ".md"

    # --- 2. CHECK SOURCE CODE (PROGRAMMING LANGUAGES) ---
    # Python (Import statements, function definitions, or typical indentation without braces)
    if "import " in clean_text and ("def " in clean_text or "if __name__" in clean_text):
        return ".py"

    # JavaScript (const/let, arrow functions, console.log)
    if "console.log" in clean_text or "const " in clean_text or "let " in clean_text:
        return ".js"

    # C / C++ (Library inclusions)
    if "#include <" in clean_text:
        if "std::" in clean_text or "cout" in clean_text:
            return ".cpp"
        return ".c"

    # Java (Class structure)
    if "public class " in clean_text and "public static void main" in clean_text:
        return ".java"

    # INI / Configuration files (Sections in brackets at the start of lines, e.g. [settings])
    if clean_text.startswith("[") and "]" in clean_text.split("\n"):
        return ".ini"

    # --- 3. CHECK CAD / 3D FORMATS ---
    # OBJ (Wavefront 3D - lines start with v, vn, vt, f)
    lines = [ln.strip() for ln in clean_text.split("\n") if ln.strip()]
    if lines and all(
        ln.startswith(("v ", "vn ", "vt ", "f ", "#")) for ln in lines[:5]
    ):
        return ".obj"

    # STL (ASCII version for 3D printing - always starts with solid)
    if clean_text.lower().startswith("solid "):
        return ".stl"

    # XYZ (Point clouds - only lines with 3 decimal numbers separated by spaces)
    if lines and re.match(r"^-?\d+\.?\d*\s+-?\d+\.?\d*\s+-?\d+\.?\d*$", lines[0]):
        return ".xyz"

    # --- 4. CHECK TABLES (CSV / TSV) ---
    first_line = lines[0] if lines else ""
    if first_line.count("\t") >= 2:
        return ".tsv"
    if first_line.count(",") >= 2 or first_line.count(";") >= 2:
        return ".csv"

    # Default text file if no specific patterns match
    return ".txt"


def process_zip(zip_bytes):
    """Unzips files in memory, fixes their extensions, and repacks them into a new ZIP."""
    input_zip = zipfile.ZipFile(io.BytesIO(zip_bytes))
    output_buffer = io.BytesIO()

    with zipfile.ZipFile(
        output_buffer, "w", zipfile.ZIP_DEFLATED
    ) as output_zip:
        for file_info in input_zip.infolist():
            # Skip directories
            if file_info.is_dir():
                continue

            # Read file content
            file_data = input_zip.read(file_info.filename)

            # Get the correct extension and strip the old one
            new_extension = guess_extended_extension(file_data)
            base_name, _ = os.path.splitext(file_info.filename)
            new_filename = base_name + new_extension

            # Write into the new ZIP archive
            output_zip.writestr(new_filename, file_data)

    output_buffer.seek(0)
    return output_buffer


@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file part in the request")
            return redirect(request.url)

        uploaded_file = request.files["file"]

        if uploaded_file.filename == "":
            flash("No file selected")
            return redirect(request.url)

        if uploaded_file:
            file_data = uploaded_file.read()
            filename = uploaded_file.filename

            # Check if the uploaded file is a ZIP archive
            if filename.lower().endswith(".zip"):
                processed_zip_buffer = process_zip(file_data)
                clean_name, _ = os.path.splitext(filename)
                new_zip_name = f"{clean_name}_fixed.zip"

                return send_file(
                    processed_zip_buffer,
                    as_attachment=True,
                    download_name=new_zip_name,
                    mimetype="application/zip",
                )

            # Process as a single standalone file
            new_extension = guess_extended_extension(file_data)
            clean_filename, _ = os.path.splitext(filename)
            new_filename = clean_filename + new_extension

            # Save temporarily and send back
            temp_path = os.path.join(
                "/tmp" if os.name != "nt" else ".", new_filename
            )
            with open(temp_path, "wb") as f:
                f.write(file_data)

            return send_file(
                temp_path, as_attachment=True, download_name=new_filename
            )

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
