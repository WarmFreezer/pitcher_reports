from xhtml2pdf import pisa
import os

def create_pitcher_pdf_from_html(pitcher_name, pitcher_id, table_html, image_path, output_path):
    """
    Create PDF from HTML content
    """
    # Make image path absolute or use file:// protocol
    abs_image_path = os.path.abspath(image_path)

    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ 
                font-family: Arial, sans-serif; 
                margin: 0;
                padding: 20px;
                background-color: #FFFFFF;
            }}

            @page {{
                size: portrait;
                margin: 0.5in;
            }}
            h1 {{ 
                color: #FFCF00; 
                text-align: center;
                margin-bottom: 20px;
            }}
            .heatmap {{
                text-align: center;
                margin: 20px 0;
            }}
            .heatmap img {{ 
                max-width: 100%; 
                height: auto;
            }}

            table {{ 
                width: 100%; 
                border-collapse: collapse; 
                margin: 20px 0;
                font-size: 10px;
            }}
            th {{
                background-color: #004080;
                color: white;
                padding: 8px;
                text-align: center;
                font-weight: bold;
            }}
            td {{
                border: 1px solid #ddd;
                padding: 6px;
                text-align: center;
            }}
            tr:nth-child(even) {{ 
                background-color: #f9f9f9; 
            }}
           
            .header-table {{
                border: none;
                width: 100%;
                height: 100px;
                background-color: #004080;
            }}
            .header-table td {{
                border: none;
                vertical-align: middle;
                text-align: center;
                padding: 10px;
            }}
            .header-table tr {{
                border: none;
            }}
            .header-center {{
                color: #FFCF00;
                font-family: 'Graduate', serif;
                font-size: 24px;
            }}
        </style>
    </head>
    <body>
        <table class="header-table">
            <tr>
                <td class="header-left">
                    <img src="app/static/resources/favicon.ico" height="128" alt="PFP">
                </td>
                <td class="header-center">
                    <h1>Pitcher Report for {pitcher_name}</h1>
                </td>
                <td class="header-right">
                    <img src="app/static/resources/strutting_eagle.png" height="128" alt="Strutting Eagle">
                </td>
            </tr>
        </table>

        <main>
            <div class="heatmap">
                <img src="{image_path}" alt="Heat Map" width="800">
            </div>
            {table_html}
        </main>

    </body>
    </html>
    """
    
    with open(output_path, "wb") as pdf_file:
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_file)
    
    if pisa_status.err:
        print(f"Error creating PDF: {output_path}")
        return False
    else:
        print(f"PDF created successfully: {output_path}")
        return True

def merge_pdfs(pdf_folder, output_path):
    """
    Merge multiple PDFs into one
    """
    from PyPDF2 import PdfMerger
    
    merger = PdfMerger()
    
    for pdf in sorted(os.listdir(pdf_folder)):
        if pdf == os.path.basename(output_path):
            continue

        pdf_path = os.path.join(pdf_folder, pdf)
        if os.path.exists(pdf_path) and pdf_path.endswith('.pdf'):
            merger.append(pdf_path)
    
    merger.write(output_path)
    merger.close()
    print(f"Merged PDF created: {output_path}")