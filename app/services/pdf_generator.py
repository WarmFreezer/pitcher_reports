from xhtml2pdf import pisa
from io import BytesIO
import os
import base64

def create_pitcher_pdf_from_html(current_user, pitcher_name, pitcher_id, table_html, output_path, branding):
    """
    Create PDF from HTML content
    """

    if os.path.exists(os.path.join('app', 'storage', 'schools', current_user.school.slug, 'players', str(pitcher_id), 'pfp.png')):
        player_pfp = os.path.join('app', 'storage', 'schools', current_user.school.slug, 'players', str(pitcher_id), 'pfp.png')
    else:
        player_pfp = os.path.join('app', 'static', 'resources', 'favicon.ico')

    primary_color = branding['colors']['primary']
    secondary_color = branding['colors']['secondary']
    tertiary_color = branding['colors']['tertiary']
    accent_color = branding['colors']['accent']
    light_color = branding['colors']['light']
    dark_color = branding['colors']['dark']
    
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
                color: {secondary_color};
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
            th {{
                background-color: {accent_color};
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
                height: 100px;
                background-color: {accent_color};
            }}
            .header-table td {{
                border: none;
                vertical-align: middle;
                text-align: center;
                padding: 8px;
                background-color: {accent_color};
            }}
            .header-center {{
                color: {secondary_color};
                font-family: 'Graduate', serif;
                font-size: 24px;
            }}
        </style>
    </head>
    <body>
        <table class="header-table">
            <tr>
                <td class="header-left">
                    <img src="{player_pfp}" height="128" alt="PFP">
                </td>
                <td width="60%">
                    <h1>Pitcher Report for {pitcher_name}</h1>
                </td>
                <td class="header-right">
                    <img src="app/storage/schools/{current_user.school.slug}/assets/logo.png" height="128" alt="{current_user.school.slug} Logo">
                </td>
            </tr>
        </table>

        <main>
            <div class="heatmap">
                <img src="app/storage/schools/{current_user.school.slug}/temp/{current_user.id}_pitcher_{pitcher_id}_heat_map.png" alt="Heat Map" width="800">
            </div>
            {table_html}
        </main>

    </body>
    </html>
    """
    
    with open(output_path, "wb") as pdf_file:
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_file)
    
    if pisa_status.err:
        print(f"Error creating PDF: {os.path.basename(output_path)}")
        return False
    else:
        print(f"PDF created successfully: {os.path.basename(output_path)}")
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
    print(f"Merged PDF created: {os.path.basename(output_path)}")