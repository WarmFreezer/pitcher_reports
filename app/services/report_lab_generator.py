import os
import base64
import pandas as pd
from PIL import Image as PILImage
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle,
    Image, Frame, PageTemplate, BaseDocTemplate, KeepInFrame
)

from .branding_loader import BrandingLoader

STORAGE_SCHOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'storage', 'schools')
STATIC_RESOURCES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'static', 'resources')

class PDF_Generator:
    PAGE_W, PAGE_H = letter
    MARGIN = 0.65 * inch
    IMG_WIDTH = 2.5 * inch
    WHITE = colors.HexColor("#FFFFFF")
    BLACK = colors.HexColor("#000000")

    '''
    usage_data, table_data, output_path,
            self.left_usage_html = usage_data[0]
            self.right_usage_html = usage_data[1]
                    
            year = table_data[0].split('-')[0]
            month = table_data[0].split('-')[1]
            day = table_data[0].split('-')[2]

            self.date = month + '/' + day + '/' + year
            self.home_team = table_data[1]
            self.away_team = table_data[2]
            self.pitcher_name = table_data[3]
            self.table_html = table_data[4].to_html(index=False, classes="dataframe", border=0, float_format="{:.2f}".format)

        self.output_path = output_path
    '''

    def __init__(self, current_user, branding):
        self.current_user = current_user

        # Always resolve logo from local storage; fall back to the app icon if not yet uploaded
        logo_path = os.path.join(STORAGE_SCHOOLS, current_user.school.slug, 'assets', 'logo.png')
        self.school_logo = logo_path if os.path.exists(logo_path) else os.path.join(STATIC_RESOURCES, 'statline-logo.png')

        self.primary_color = colors.HexColor(branding['colors']['primary'])
        self.secondary_color = colors.HexColor(branding['colors']['secondary'])
        self.tertiary_color = colors.HexColor(branding['colors']['tertiary'])
        self.accent_color = colors.HexColor(branding['colors']['accent'])
        self.text_color = self.primary_color
        self.dark_color = colors.HexColor(branding['colors'].get('dark', '#000000'))
        self.light_color = colors.HexColor(branding['colors'].get('light', '#FFFFFF'))

        self.styles = {
            "title": ParagraphStyle(
                "ReportTitle",
                fontSize=22, textColor=self.WHITE,
                fontName="Helvetica-Bold",
                alignment=TA_LEFT, leading=26,
            ),
            "subtitle": ParagraphStyle(
                "ReportSubtitle",
                fontSize=11, textColor=self.primary_color,
                fontName="Helvetica",
                alignment=TA_LEFT, leading=14,
            ),
            "section_header": ParagraphStyle(
                "SectionHeader",
                fontSize=12, textColor=self.tertiary_color,
                fontName="Helvetica-Bold",
                spaceBefore=14, spaceAfter=6,
                borderPad=4,
            ),
            "body": ParagraphStyle(
                "Body",
                fontSize=9, textColor=self.dark_color,
                fontName="Helvetica",
                leading=13,
            ),
            "stat_label": ParagraphStyle(
                "StatLabel",
                fontSize=8, textColor=self.secondary_color,
                fontName="Helvetica",
                alignment=TA_CENTER,
            ),
            "stat_value": ParagraphStyle(
                "StatValue",
                fontSize=18, textColor=self.tertiary_color,
                fontName="Helvetica-Bold",
                alignment=TA_CENTER,
            ),
            "table_header": ParagraphStyle(
                "TableHeader",
                fontSize=9, textColor=self.WHITE,
                fontName="Helvetica-Bold",
                alignment=TA_CENTER,
            ),
            "table_cell": ParagraphStyle(
                "TableCell",
                fontSize=9, textColor=self.tertiary_color,
                fontName="Helvetica",
                alignment=TA_CENTER,
            ),
            "footer": ParagraphStyle(
                "Footer",
                fontSize=7, textColor=self.dark_color,
                fontName="Helvetica",
                alignment=TA_CENTER,
            ),
        }

    def generate_header(self, player_pfp: str, pitcher_name: str, school_logo: str, game_date: str, home_team: str, away_team: str) -> list:
        """
        Generate document header with pitcher info and game details.

        Args:
            player_pfp: URL or path to player's profile picture
            pitcher_name: Name of the pitcher
            school_logo: URL or path to school's logo
            game_date: Game date in MM/DD/YYYY format
            home_team: Home team name
            away_team: Away team name
            
        Returns:
            List of document elements for the header
        """
        elements = []
        
        # Create center column content with title and subtitle stacked vertically
        center_content = [
            Paragraph(f"<b>{pitcher_name}</b>", self.styles["title"]),
            Spacer(1, 0.05 * inch),
            Paragraph(f"{game_date} | {home_team} @ {away_team}", self.styles["subtitle"]),
        ]
        
        def _fit_image(path, box=1*inch):
            img = PILImage.open(path)
            w, h = img.size
            if w >= h:
                return Image(path, width=box, height=box * h / w)
            else:
                return Image(path, width=box * w / h, height=box)

        # Create header with PFP on left, text in center, school logo on right
        header_data = [[
            _fit_image(player_pfp),
            center_content,
            _fit_image(school_logo),
        ]]

        header_table = Table(header_data, colWidths=[1.25*inch, self.PAGE_W - 2.5*inch, 1.25*inch])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.tertiary_color),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.WHITE),
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('ALIGN', (2, 0), (2, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (0, 0), 30),
            ('RIGHTPADDING', (0, 0), (0, 0), 15),
            ('LEFTPADDING', (1, 0), (1, 0), 10),
            ('RIGHTPADDING', (1, 0), (1, 0), 10),
            ('LEFTPADDING', (2, 0), (2, 0), 15),
            ('RIGHTPADDING', (2, 0), (2, 0), 30),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('LINEBELOW', (0, 0), (-1, 0), 4, self.secondary_color),
        ]))
        header_table.spaceAfter = 0
        header_table.spaceBefore = 0

        elements.append(header_table)
        elements.append(Spacer(1, 0.05 * inch))
        
        return elements

    def generate_pitcher_stats_table(self, stats_df) -> list:
        """
        Generate a table displaying pitcher statistics from a DataFrame.
        
        Args:
            stats_df: DataFrame with columns: Pitch, Count, % Thrown, Vel., IVB, HB, Spin, VAA, HAA, RelH, RelS, Ext., Axis, Zone %, Chase %, CSW %
            
        Returns:
            List of document elements containing the stats table
        """
        elements = []
        
        elements.append(Paragraph("Pitch Statistics", self.styles["section_header"]))
        
        # Prepare table data
        table_data = [list(stats_df.columns)]
        
        for _, row in stats_df.iterrows():
            row_data = []
            for col in stats_df.columns:
                value = row[col]
                # Format numeric values
                if isinstance(value, (int, float)):
                    if col in ['Thrown', 'Zone', 'Chase', 'CSW']:
                        row_data.append(f"{value:.1f}%")
                    elif col == 'Count':
                        row_data.append(str(int(value)))
                    else:
                        row_data.append(f"{value:.2f}")
                else:
                    row_data.append(str(value))
            table_data.append(row_data)
        
        # Create table
        col_widths = [(self.PAGE_W - 2 * self.MARGIN) / len(stats_df.columns)]
        stats_table = Table(table_data, colWidths=col_widths)
        
        # Style the table
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), self.tertiary_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.WHITE),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [self.WHITE, self.light_color]),
        ]

        stats_table.setStyle(TableStyle(table_style))
        elements.append(stats_table)
        elements.append(Spacer(1, 0.05 * inch))
        
        return elements

    def generate_usage_table(self, usage_df, batter_side: str = "Right", available_width: float = None) -> list:
        """
        Generate a table displaying pitch usage by count.
        
        Args:
            usage_df: DataFrame with usage statistics
            batter_side: "Left" or "Right" handed batters
            
        Returns:
            List of document elements containing the usage table
        """
        elements = []
        
        elements.append(Paragraph(f"Pitch Usage vs {batter_side}-Handed Batters", self.styles["section_header"]))
        
        # Prepare table data
        table_data = [list(usage_df.columns)]
        
        for _, row in usage_df.iterrows():
            row_data = []
            for col in usage_df.columns:
                value = row[col]
                # Format numeric values
                if isinstance(value, (int, float)):
                    if col in ['Strike', '0-0', "Hitter's", "Pitcher's", '2k', 'Whiff']:
                        row_data.append(f"{value:.1f}%")
                    elif col == 'Count':
                        row_data.append(str(int(value)))
                    else:
                        row_data.append(f"{value:.2f}")
                else:
                    row_data.append(str(value))
            table_data.append(row_data)
        
        # Create table with adjusted column widths
        if available_width is None:
            available_width = (self.PAGE_W - 2 * self.MARGIN) / 2
        col_widths = available_width / len(usage_df.columns)
        usage_table = Table(table_data, colWidths=col_widths)
        
        # Style the table
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), self.tertiary_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.WHITE),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [self.WHITE, self.light_color]),
        ]

        usage_table.setStyle(TableStyle(table_style))
        elements.append(usage_table)
        elements.append(Spacer(1, 0.05 * inch))
        
        return elements

    def generate_stats_grid(self, stats_data: dict) -> list:
        """
        Generate a grid of key statistical boxes.
        
        Args:
            stats_data: Dictionary with stat names as keys and values as values
                       Example: {"Avg Velocity": "94.2", "Spin Rate": "2456", ...}
        
        Returns:
            List of document elements containing the stats grid
        """
        elements = []
        
        elements.append(Paragraph("Key Statistics", self.styles["section_header"]))
        
        # Create a grid of stats (4 columns)
        stat_items = list(stats_data.items())
        grid_data = []
        
        for i in range(0, len(stat_items), 4):
            row = []
            for j in range(4):
                if i + j < len(stat_items):
                    label, value = stat_items[i + j]
                    stat_cell = [
                        Paragraph(str(value), self.styles["stat_value"]),
                        Paragraph(label, self.styles["stat_label"])
                    ]
                    row.append(stat_cell)
                else:
                    row.append(["", ""])
            grid_data.append(row)
        
        # Create table for stats grid
        col_width = (self.PAGE_W - 2 * self.MARGIN) / 4
        stats_grid_table = Table(grid_data, colWidths=[col_width] * 4)
        
        stats_grid_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.accent_color),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, self.light_color),
        ]))
        
        elements.append(stats_grid_table)
        elements.append(Spacer(1, 0.05 * inch))
        
        return elements

    def add_image_section(self, image_path: str, title: str, max_width_pts: float = None) -> list:
        """
        Add an image section to the report (for heat maps, break maps, etc).
        
        Args:
            image_path: Full path to the image file
            title: Title for the image section
            max_width_pts: Maximum width of the image in points
            
        Returns:
            List of document elements containing the image section
        """
        elements = []
        
        if max_width_pts is None:
            max_width_pts = self.PAGE_W - 2 * self.MARGIN

        if not os.path.exists(image_path):
            elements.append(Paragraph(f"<i>Image not found: {title}</i>", self.styles["body"]))
            return elements
        
        try:
            elements.append(Paragraph(title, self.styles["section_header"]))
            
            # Calculate height to maintain aspect ratio
            from PIL import Image as PILImage
            img = PILImage.open(image_path)
            aspect_ratio = img.height / img.width
            img_w = max_width_pts
            img_h = img_w * aspect_ratio
            
            max_height_pts = (self.PAGE_H - 2 * self.MARGIN) / 3.5
            if img_h > max_height_pts:
                img_h = max_height_pts
                img_w = img_h / aspect_ratio

            # Add image
            img_element = Image(image_path, width=img_w, height=img_h)
            elements.append(img_element)
            elements.append(Spacer(1, 0.05 * inch))
            
        except Exception as e:
            elements.append(Paragraph(f"<i>Error loading image: {str(e)}</i>", self.styles["body"]))
        
        return elements

    def generate_pitch_type_summary(self, stats_df) -> list:
        """
        Generate a summary section showing pitch type breakdown.
        
        Args:
            stats_df: DataFrame with pitch statistics
            
        Returns:
            List of document elements
        """
        elements = []
        
        elements.append(Paragraph("Pitch Type Breakdown", self.styles["section_header"]))
        
        # Create pitch breakdown table
        summary_data = [['Pitch Type', 'Count', '% of Total']]
        
        total_pitches = stats_df['Count'].sum() if 'Count' in stats_df.columns else 0
        
        for _, row in stats_df.iterrows():
            pitch_name = str(row.get('Pitch', ''))
            count = row.get('Count', 0)
            pct = (count / total_pitches * 100) if total_pitches > 0 else 0
            
            summary_data.append([
                pitch_name,
                str(int(count)),
                f"{pct:.1f}%"
            ])
        
        summary_table = Table(summary_data, colWidths=[(self.PAGE_W - 2 * self.MARGIN) / 3] * 3)
        
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.accent_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.WHITE),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [self.WHITE, self.tertiary_color]),
        ]))
        
        elements.append(summary_table)
        elements.append(Spacer(1, 0.05 * inch))
        
        return elements

    def generate_summary_page(self, pitcher_name: str, game_info: dict, stats_df=None) -> list:
        """
        Generate a summary page with key highlights.
        
        Args:
            pitcher_name: Name of the pitcher
            game_info: Dictionary with game information (date, teams, etc)
            stats_df: Optional DataFrame with statistics
            
        Returns:
            List of document elements
        """
        elements = []
        
        # Add main header
        elements.extend(self.generate_header(
            pitcher_name,
            game_info.get('game_date', ''),
            game_info.get('home_team', ''),
            game_info.get('away_team', '')
        ))
        
        # Add summary text
        summary_text = f"""
        <b>Game Summary:</b><br/>
        {pitcher_name} pitched for the {game_info.get('home_team', 'home team')}.
        """
        
        if stats_df is not None and len(stats_df) > 0:
            total_pitches = stats_df['Count'].sum()
            avg_velocity = stats_df['Vel.'].mean() if 'Vel.' in stats_df.columns else 0
            summary_text += f"<br/>Total Pitches: {int(total_pitches)} | Avg Velocity: {avg_velocity:.1f} mph"
        
        elements.append(Paragraph(summary_text, self.styles["body"]))
        elements.append(Spacer(1, 0.05 * inch))
        
        return elements

    def generate_two_column_layout(self, left_elements: list, right_elements: list) -> list:
        """
        Generate a two-column layout for side-by-side content.
        
        Args:
            left_elements: List of flowable elements for left column
            right_elements: List of flowable elements for right column
            
        Returns:
            List containing a table with two columns
        """
        col_width = (self.PAGE_W - 2 * self.MARGIN - 0.2 * inch) / 2
        
        # Wrap elements in KeepInFrame to constrain width for table cells
        left_frame = KeepInFrame(col_width, self.PAGE_H, left_elements, hAlign='LEFT')
        right_frame = KeepInFrame(col_width, self.PAGE_H, right_elements, hAlign='LEFT')
        
        layout_table = Table(
            [[left_frame, right_frame]],
            colWidths=[col_width, col_width],
            rowHeights=[None]
        )
        
        layout_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        
        return [layout_table]

    def generate_pitcher_report(self, data: dict, output_path: str) -> str:
        """
        Generate complete pitcher report PDF.
        
        Args:
            data: Dictionary containing report data with keys:
                  - pitcher_name: str
                  - pitcher_id: int
                  - date: str (MM/DD/YYYY)
                  - home_team: str
                  - away_team: str
                  - pitch_stats: pandas DataFrame with pitch statistics
                  - pitch_usage_left: pandas DataFrame for left-handed batters usage
                  - pitch_usage_right: pandas DataFrame for right-handed batters usage
                  - overview: dict of key statistics (optional)
                  - pitch_heat_map: image paths (optional)
                  - pitch_break_map: image paths (optional)

            output_path: Full path where PDF should be saved
            
        Returns:
            Path to the generated PDF
        """
        
        # Resolve player pfp: player photo → school logo → statline logo
        pfp_path = os.path.join(STORAGE_SCHOOLS, self.current_user.school.slug, 'assets', 'players', str(data.get('pitcher_id')), 'pfp.png')
        player_pfp = pfp_path if os.path.exists(pfp_path) else self.school_logo

        # Replace SimpleDocTemplate with this in generate_pitcher_report:
        frame = Frame(
            self.MARGIN,
            0,
            self.PAGE_W - 2 * self.MARGIN,
            self.PAGE_H,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )

        pdf_file = BaseDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=self.MARGIN,
            leftMargin=self.MARGIN,
            topMargin=0,
            bottomMargin=0,
        )
        pdf_file.addPageTemplates([PageTemplate(id='main', frames=[frame])])
        
        elements = []
        
        print(f"[PDF] Starting report generation")
        print(f"[PDF] Data keys: {list(data.keys())}")
        
        # Add header
        elements.extend(self.generate_header(
            player_pfp,
            data.get('pitcher_name', 'Pitcher'),
            self.school_logo,
            data.get('date', ''),
            data.get('home_team', ''),
            data.get('away_team', '')
        ))
        print(f"[PDF] Header added. Total elements: {len(elements)}")
        
        # Add pitch heatmap images (left and right) below header
        half_width = (self.PAGE_W - 2 * self.MARGIN - 0.2 * inch) / 2
        heatmap_left = data.get('pitch_heat_map_left')
        heatmap_right = data.get('pitch_heat_map_right')
        if heatmap_left or heatmap_right:
            left_els = self.add_image_section(heatmap_left, "vs Left-Handed Batters", max_width_pts=half_width) if heatmap_left else []
            right_els = self.add_image_section(heatmap_right, "vs Right-Handed Batters", max_width_pts=half_width) if heatmap_right else []
            elements.extend(self.generate_two_column_layout(left_els, right_els))
            print(f"[PDF] Added pitch heat map images: {heatmap_left}, {heatmap_right}")

        # Add pitch break map on left below heatmap and usage tables on right if break map exists
        break_map_path = data.get('pitch_break_map')    
        if break_map_path and os.path.exists(break_map_path):
            half_width = (self.PAGE_W - 2 * self.MARGIN - 0.2 * inch) / 2
            left_elements = self.add_image_section(break_map_path, "Pitch Break Map", max_width_pts=half_width)
            right_elements = []
            if 'pitch_usage_left' in data and isinstance(data['pitch_usage_left'], pd.DataFrame):
                right_elements.extend(self.generate_usage_table(data['pitch_usage_left'], batter_side="Left"))
            if 'pitch_usage_right' in data and isinstance(data['pitch_usage_right'], pd.DataFrame):
                right_elements.extend(self.generate_usage_table(data['pitch_usage_right'], batter_side="Right"))
            
            elements.extend(self.generate_two_column_layout(left_elements, right_elements))
            print(f"[PDF] Added pitch break map and usage tables")
        else:
            # If no break map, add usage tables in single column
            if 'pitch_usage_left' in data and isinstance(data['pitch_usage_left'], pd.DataFrame):
                elements.extend(self.generate_usage_table(data['pitch_usage_left'], batter_side="Left"))
            if 'pitch_usage_right' in data and isinstance(data['pitch_usage_right'], pd.DataFrame):
                elements.extend(self.generate_usage_table(data['pitch_usage_right'], batter_side="Right"))
            print(f"[PDF] Added usage tables without break map")

        # Add pitch stats table
        if 'pitch_stats' in data and isinstance(data['pitch_stats'], pd.DataFrame):
            elements.extend(self.generate_pitcher_stats_table(data['pitch_stats']))
            print(f"[PDF] Added pitch stats table")
        
        print(f"[PDF] Building PDF with {len(elements)} elements")
        
        # Build PDF
        try:
            for i, el in enumerate(elements):
                try:
                    el.wrap(self.PAGE_W - 2 * self.MARGIN, self.PAGE_H)
                except Exception as e:
                    print(f"Element {i} failed: {type(el).__name__} — {e}")

            pdf_file.build(elements)
            print(f"[PDF] PDF built successfully!")
            return output_path
        except Exception as e:
            print(f"Error generating PDF: {str(e)}")
            raise

    def generate_color_preview(self, output_path: str) -> str:
        """
        Generate a one-page sample PDF with placeholder data so users can preview
        how their branding colors will look in a real report.
        """
        frame = Frame(
            self.MARGIN, 0,
            self.PAGE_W - 2 * self.MARGIN, self.PAGE_H,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )
        doc = BaseDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=self.MARGIN, leftMargin=self.MARGIN,
            topMargin=0, bottomMargin=0,
        )
        doc.addPageTemplates([PageTemplate(id='main', frames=[frame])])

        player_pfp = os.path.join(STATIC_RESOURCES, 'favicon.png')

        elements = []
        elements.extend(self.generate_header(
            player_pfp, 'Sample Pitcher', self.school_logo,
            '01/01/2025', 'HOME', 'AWAY',
        ))

        stats_df = pd.DataFrame({
            'Pitch':  ['Fastball', 'Slider', 'Curveball', 'Changeup'],
            'Count':  [45,          20,        15,           10],
            'Thrown': [50.0,        22.2,      16.7,         11.1],
            'Vel.':   [93.2,        84.1,      77.5,         85.0],
            'IVB':    [14.5,         2.1,      -8.3,          7.2],
            'HB':     [ 8.3,        -5.6,       6.1,         -3.4],
            'Spin':   [2345.0,     2567.0,    2789.0,       1876.0],
            'VAA':    [-4.2,        -5.1,      -6.8,         -4.9],
            'HAA':    [ 0.3,        -1.2,       0.8,         -0.5],
            'RelH':   [ 6.1,         6.0,       5.9,          6.1],
            'RelS':   [-2.1,        -2.0,      -2.2,         -2.0],
            'Ext.':   [ 6.8,         6.5,       6.3,          6.7],
            'Axis':   [212.0,        45.0,     315.0,        190.0],
            'Zone':   [45.6,        38.2,      52.1,         41.3],
            'Chase':  [32.1,        41.5,      35.8,         28.9],
            'CSW':    [28.4,        35.2,      31.6,         25.7],
        })
        elements.extend(self.generate_pitcher_stats_table(stats_df))

        usage_cols = ['Pitch', 'Count', 'Strike', '0-0', "Hitter's", "Pitcher's", '2k', 'Whiff']
        lhh = pd.DataFrame([
            ['Fastball',  24, 65.2, 55.0, 52.0, 62.0, 58.0, 18.5],
            ['Slider',    10, 70.1, 30.0, 28.0, 38.0, 45.0, 32.4],
            ['Curveball',  8, 62.5, 25.0, 22.0, 35.0, 48.0, 28.6],
            ['Changeup',   5, 60.0, 20.0, 18.0, 28.0, 35.0, 22.1],
        ], columns=usage_cols)
        rhh = pd.DataFrame([
            ['Fastball',  21, 63.8, 52.0, 49.0, 60.0, 55.0, 20.1],
            ['Slider',    10, 68.4, 32.0, 30.0, 40.0, 43.0, 30.8],
            ['Curveball',  7, 60.0, 23.0, 20.0, 32.0, 46.0, 26.4],
            ['Changeup',   5, 58.2, 18.0, 16.0, 26.0, 33.0, 21.5],
        ], columns=usage_cols)

        half_width = (self.PAGE_W - 2 * self.MARGIN - 0.2 * inch) / 2
        # Subtract the 5pt left+right cell padding from generate_two_column_layout
        usage_width = half_width - 10
        left_els = self.generate_usage_table(lhh, batter_side="Left", available_width=usage_width)
        right_els = self.generate_usage_table(rhh, batter_side="Right", available_width=usage_width)
        elements.extend(self.generate_two_column_layout(left_els, right_els))

        doc.build(elements)
        return output_path


def find_image_with_extensions(base_path, extensions=None):
    """Find an image file with any of the given extensions"""
    if extensions is None:
        extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    
    for ext in extensions:
        path = base_path + ext
        if os.path.exists(path):
            return path
    return None

def image_to_base64(img):
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"

def merge_pdfs(id, pdf_folder, output_path):
    """
    Merge multiple PDFs into one
    """
    from PyPDF2 import PdfMerger
    
    merger = PdfMerger()
    
    for pdf in sorted(os.listdir(pdf_folder)):
        if pdf == os.path.basename(output_path):
            continue

        pdf_path = os.path.join(pdf_folder, pdf)
        if os.path.exists(pdf_path) and pdf_path.endswith('.pdf') and pdf.startswith(f"{id}_pitcher_"):
            merger.append(pdf_path)
    
    merger.write(output_path)
    merger.close()
    print(f"Merged PDF created: {os.path.basename(output_path)}")

