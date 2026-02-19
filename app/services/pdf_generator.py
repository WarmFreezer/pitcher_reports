from xhtml2pdf import pisa
from io import BytesIO
import os
import base64

def create_pitcher_pdf_from_html(school_slug, pitcher_name, pitcher_id, table_html, output_path, branding):
    """
    Create PDF from HTML content
    """
<<<<<<< HEAD
    # Make image path absolute
    abs_image_path = os.path.abspath(image_path)
    
    # Clean up the pandas table HTML for better xhtml2pdf compatibility
    # Remove inline styles that conflict with our CSS
    table_html = table_html.replace('style="text-align: left;"', '')
    table_html = table_html.replace('style="text-align: right;"', '')
    table_html = table_html.replace('style="text-align: center;"', '')
=======

    if os.path.exists(os.path.join('app', 'storage', 'schools', school_slug, 'players', str(pitcher_id), 'pfp.png')):
        player_pfp = os.path.join('app', 'storage', 'schools', school_slug, 'players', str(pitcher_id), 'pfp.png')
    else:
        player_pfp = os.path.join('app', 'static', 'resources', 'favicon.ico')

    primary_color = branding['colors']['primary']
    secondary_color = branding['colors']['secondary']
    tertiary_color = branding['colors']['tertiary']
    accent_color = branding['colors']['accent']
    light_color = branding['colors']['light']
    dark_color = branding['colors']['dark']
>>>>>>> 314a676955ddc5f5805307103a108e99ff13efd7
    
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
<<<<<<< HEAD
            
            table.dataframe thead {{
                background-color: #004080;
            }}
            
            table.dataframe th {{
                background-color: #004080;
=======
            th {{
                background-color: {accent_color};
>>>>>>> 314a676955ddc5f5805307103a108e99ff13efd7
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
<<<<<<< HEAD
                border: none;
                background-color: #004080;
                margin: 0 0 10px 0;
                padding: 10px;
=======
                height: 100px;
                background-color: {accent_color};
>>>>>>> 314a676955ddc5f5805307103a108e99ff13efd7
            }}
            .header-table td {{
                border: none;
                vertical-align: middle;
                text-align: center;
                padding: 8px;
                background-color: #004080;
            }}
<<<<<<< HEAD
            .header-table img {{
                height: 80px;
=======
            .header-center {{
                color: {secondary_color};
                font-family: 'Graduate', serif;
                font-size: 24px;
>>>>>>> 314a676955ddc5f5805307103a108e99ff13efd7
            }}
        </style>
    </head>
    <body>
        <table class="header-table">
            <tr>
<<<<<<< HEAD
                <td width="20%">
                    <img src="app/static/resources/favicon.ico" alt="Logo">
=======
                <td class="header-left">
                    <img src="{player_pfp}" height="128" alt="PFP">
>>>>>>> 314a676955ddc5f5805307103a108e99ff13efd7
                </td>
                <td width="60%">
                    <h1>Pitcher Report for {pitcher_name}</h1>
                </td>
<<<<<<< HEAD
                <td width="20%">
                    <img src="app/static/resources/strutting_eagle.png" alt="Eagle">
=======
                <td class="header-right">
                    <img src="app/storage/schools/{school_slug}/assets/logo.png" height="128" alt="{school_slug} Logo">
>>>>>>> 314a676955ddc5f5805307103a108e99ff13efd7
                </td>
            </tr>
        </table>

<<<<<<< HEAD
        <div class="heatmap">
            <img src="{abs_image_path}" alt="Heat Map">
        </div>
        
        {table_html}
=======
        <main>
            <div class="heatmap">
                <img src="app/storage/schools/{school_slug}/temp/pitcher_{pitcher_id}_heat_map.png" alt="Heat Map" width="800">
            </div>
            {table_html}
        </main>
>>>>>>> 314a676955ddc5f5805307103a108e99ff13efd7

    </body>
    </html>
    """
    
<<<<<<< HEAD
    print(html_content)


=======
    with open(output_path, "wb") as pdf_file:
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_file)
    
    if pisa_status.err:
        print(f"Error creating PDF: {os.path.basename(output_path)}")
        return False
    else:
        print(f"PDF created successfully: {os.path.basename(output_path)}")
        return True
>>>>>>> 314a676955ddc5f5805307103a108e99ff13efd7

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