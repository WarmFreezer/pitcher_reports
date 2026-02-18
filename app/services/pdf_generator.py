from xhtml2pdf import pisa
from io import BytesIO
import os

def create_pitcher_pdf_from_html(pitcher_name, pitcher_id, table_html, image_path, output_path):
    """
    Create PDF from HTML content
    """
    # Make image path absolute
    abs_image_path = os.path.abspath(image_path)
    
    # Clean up the pandas table HTML for better xhtml2pdf compatibility
    # Remove inline styles that conflict with our CSS
    table_html = table_html.replace('style="text-align: left;"', '')
    table_html = table_html.replace('style="text-align: right;"', '')
    table_html = table_html.replace('style="text-align: center;"', '')
    
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
                size: letter portrait;
                margin: 0.5in;
            }}
            
            * {{
                margin: 0;
                padding: 0;
            }}
            
            body {{ 
                font-family: Helvetica, Arial, sans-serif; 
                padding: 10px;
            }}
            
            h1 {{ 
                color: #FFCF00; 
                text-align: center;
                margin: 0;
                padding: 0;
                font-size: 24px;
            }}
            .heatmap {{
                text-align: center;
                margin: 15px 0;
                padding: 0;
            }}
            .heatmap img {{ 
                width: 90%;
                height: auto;
            }}

            /* Table styling optimized for xhtml2pdf */
            table.dataframe {{ 
                width: 100%; 
                border-collapse: collapse; 
                margin: 15px 0 0 0;
                font-size: 9px;
                border: 1px solid #ddd;
            }}
            
            table.dataframe thead {{
                background-color: #004080;
            }}
            
            table.dataframe th {{
                background-color: #004080;
                color: white;
                padding: 6px 4px;
                text-align: center;
                font-weight: bold;
                border: 1px solid #003060;
                font-size: 9px;
            }}
            
            table.dataframe td {{
                border: 1px solid #ddd;
                padding: 5px 4px;
                text-align: center;
                font-size: 9px;
            }}
            
            table.dataframe tbody tr:nth-child(even) td {{ 
                background-color: #f5f5f5; 
            }}
            
            table.dataframe tbody tr:nth-child(odd) td {{ 
                background-color: white; 
            }}
            .header-table {{
                width: 100%;
                border: none;
                background-color: #004080;
                margin: 0 0 10px 0;
                padding: 10px;
            }}
            .header-table td {{
                border: none;
                vertical-align: middle;
                text-align: center;
                padding: 8px;
                background-color: #004080;
            }}
            .header-table img {{
                height: 80px;
            }}
        </style>
    </head>
    <body>
        <table class="header-table">
            <tr>
                <td width="20%">
                    <img src="app/static/resources/favicon.ico" alt="Logo">
                </td>
                <td width="60%">
                    <h1>Pitcher Report for {pitcher_name}</h1>
                </td>
                <td width="20%">
                    <img src="app/static/resources/strutting_eagle.png" alt="Eagle">
                </td>
            </tr>
        </table>

        <div class="heatmap">
            <img src="{abs_image_path}" alt="Heat Map">
        </div>
        
        {table_html}

    </body>
    </html>
    """
    
    print(html_content)

    try:
        with open(output_path, "wb") as pdf_file:
            pisa_status = pisa.CreatePDF(
                html_content.encode('utf-8'),
                dest=pdf_file,
                encoding='utf-8'
            )
        
        if pisa_status.err:
            print(f"Error creating PDF: {output_path}")
            return False
        else:
            print(f"PDF created successfully: {output_path}")
            return True
    except Exception as e:
        print(f"Error creating PDF: {output_path} - {e}")
        return False

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