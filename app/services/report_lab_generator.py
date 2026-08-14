import os
import base64
from typing import Any

import pandas as pd
from PIL import Image as PILImage
from io import BytesIO
import io

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle,
    Image, Frame, PageTemplate, BaseDocTemplate, KeepInFrame
)

from app.db.models import User
from app.services.pitch_stats import (
    PitcherReportRequest,
    PitcherStatsTable,
    PitchTypeStat,
    PitchUsageStat,
    PitchUsageTable,
)
from app.services.stat_table import StatTable
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

    def __init__(self, current_user: User, branding: dict[str, Any]) -> None:
        self.current_user = current_user

        # Always resolve logo from local storage; fall back to the app icon if not yet uploaded
        logo_path = os.path.join(STORAGE_SCHOOLS, str(current_user.school_id), 'assets', 'logo.png')
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
                fontSize=11, textColor=self.secondary_color,
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
            # Both need explicit leading -- ParagraphStyle defaults to 12pt, which is
            # less than the value's own font size and overlaps the label beneath it
            "stat_label": ParagraphStyle(
                "StatLabel",
                fontSize=8, textColor=self.dark_color,
                fontName="Helvetica",
                alignment=TA_CENTER, leading=10,
            ),
            "stat_value": ParagraphStyle(
                "StatValue",
                fontSize=18, textColor=self.tertiary_color,
                fontName="Helvetica-Bold",
                alignment=TA_CENTER, leading=21, spaceAfter=2,
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

    def generate_header(self, player_pfp: str, pitcher_name: str, school_logo: str, game_date: str, home_team: str, away_team: str, pitcher_height: str = '', pitcher_weight: str = '', age: int | None = None) -> list[Any]:
        """
        Generate document header with pitcher info and game details.

        Args:
            player_pfp: URL or path to player's profile picture
            pitcher_name: Name of the pitcher
            school_logo: URL or path to school's logo
            game_date: Game date in MM/DD/YYYY format
            home_team: Home team name
            away_team: Away team name
            pitcher_height: Pitcher's height
            pitcher_weight: Pitcher's weight
            age: Pitcher's age
            
        Returns:
            List of document elements for the header
        """
        elements: list[Any] = []

        # Create center column content with title and subtitle stacked vertically
        center_content = [
            Paragraph(f"<b>{pitcher_name}</b>", self.styles["title"]),
            Spacer(1, 0.05 * inch),
            Paragraph(f"{game_date} | {home_team} @ {away_team}", self.styles["subtitle"]),
            Paragraph(f"{pitcher_height} {f'| {pitcher_weight}' if pitcher_weight else ''} {f'| {age}' if age else ''}", self.styles["subtitle"]),
        ]
        
        def _fit_image(path: str, box: float = 1*inch) -> Image:
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

    def generate_pitcher_stats_table(self, stats: PitcherStatsTable) -> list[Any]:
        """Render a pitcher's per-pitch-type stats table. Formatting comes from PitcherStatsTable.columns."""
        elements: list[Any] = []

        elements.append(Paragraph("Pitch Statistics", self.styles["section_header"]))

        table_data = stats.to_reportlab_rows()

        # Create table
        col_widths = [(self.PAGE_W - 2 * self.MARGIN) / len(stats.columns)]
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

    def generate_usage_table(self, usage: PitchUsageTable, batter_side: str = "Right", available_width: float | None = None) -> list[Any]:
        """Render a pitch-usage-by-count table for one batter side. Formatting comes from PitchUsageTable.columns."""
        elements: list[Any] = []

        elements.append(Paragraph(f"Pitch Usage vs {batter_side}-Handed Batters", self.styles["section_header"]))

        table_data = usage.to_reportlab_rows()

        # Create table with adjusted column widths
        if available_width is None:
            available_width = (self.PAGE_W - 2 * self.MARGIN) / 2
        col_widths = available_width / len(usage.columns)
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

    def generate_stats_grid(self, stats_data: dict[str, Any]) -> list[Any]:
        """
        Generate a grid of key statistical boxes.

        Args:
            stats_data: Dictionary with stat names as keys and values as values
                       Example: {"Avg Velocity": "94.2", "Spin Rate": "2456", ...}

        Returns:
            List of document elements containing the stats grid
        """
        elements: list[Any] = []

        elements.append(Paragraph("Key Statistics", self.styles["section_header"]))

        # Create a grid of stats (4 columns)
        stat_items = list(stats_data.items())
        grid_data: list[Any] = []
        
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
        
        # Light tiles with dark text: accent is a saturated brand colour, and the
        # tertiary-on-accent pairing it replaced was unreadable on the default palette
        stats_grid_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.light_color),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, self.accent_color),
        ]))
        
        elements.append(stats_grid_table)
        elements.append(Spacer(1, 0.05 * inch))
        
        return elements

    def add_image_section(self, image_path: str, title: str, max_width_pts: float | None = None) -> list[Any]:
        """
        Add an image section to the report (for heat maps, break maps, etc).

        Args:
            image_path: Full path to the image file
            title: Title for the image section
            max_width_pts: Maximum width of the image in points

        Returns:
            List of document elements containing the image section
        """
        elements: list[Any] = []
        
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

    def generate_pitch_type_summary(self, stats_df: pd.DataFrame) -> list[Any]:
        """
        Generate a summary section showing pitch type breakdown.

        Args:
            stats_df: DataFrame with pitch statistics

        Returns:
            List of document elements
        """
        elements: list[Any] = []
        
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

    def generate_summary_page(self, pitcher_name: str, game_info: dict[str, Any], stats_df: pd.DataFrame | None = None) -> list[Any]:
        """
        Generate a summary page with key highlights.

        Args:
            pitcher_name: Name of the pitcher
            game_info: Dictionary with game information (date, teams, etc)
            stats_df: Optional DataFrame with statistics

        Returns:
            List of document elements
        """
        elements: list[Any] = []

        # Add main header
        elements.extend(self.generate_header(
            self.school_logo,
            pitcher_name,
            self.school_logo,
            game_info.get('game_date', ''),
            game_info.get('home_team', ''),
            game_info.get('away_team', ''),
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

    def generate_two_column_layout(self, left_elements: list[Any], right_elements: list[Any]) -> list[Any]:
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

    def generate_pitcher_report(self, data: PitcherReportRequest, output_path: str) -> str:
        """Generate complete pitcher report PDF. Returns the path it was saved to."""

        # Resolve player pfp: player photo → school logo → statline logo
        pfp_path = os.path.join(STORAGE_SCHOOLS, str(self.current_user.school_id), 'assets', 'players', str(data.pitcher_id), 'pfp.png')
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

        elements: list[Any] = []

        print(f"[PDF] Starting report generation")

        # Add header
        elements.extend(self.generate_header(
            player_pfp,
            data.pitcher_name,
            self.school_logo,
            data.date,
            data.home_team,
            data.away_team,
            data.pitcher_height,
            data.pitcher_weight,
            data.pitcher_age,
        ))
        # Add pitch heatmap images (left and right) below header
        half_width = (self.PAGE_W - 2 * self.MARGIN - 0.2 * inch) / 2
        if data.pitch_heat_map_left or data.pitch_heat_map_right:
            left_els = self.add_image_section(data.pitch_heat_map_left, "vs Left-Handed Batters", max_width_pts=half_width) if data.pitch_heat_map_left else []
            right_els = self.add_image_section(data.pitch_heat_map_right, "vs Right-Handed Batters", max_width_pts=half_width) if data.pitch_heat_map_right else []
            elements.extend(self.generate_two_column_layout(left_els, right_els))

        # Add pitch break map on left below heatmap and usage tables on right if break map exists
        if data.pitch_break_map and os.path.exists(data.pitch_break_map):
            half_width = (self.PAGE_W - 2 * self.MARGIN - 0.2 * inch) / 2
            left_elements = self.add_image_section(data.pitch_break_map, "Pitch Break Map", max_width_pts=half_width)
            right_elements: list[Any] = []
            if data.pitch_usage_left is not None:
                right_elements.extend(self.generate_usage_table(data.pitch_usage_left, batter_side="Left"))
            if data.pitch_usage_right is not None:
                right_elements.extend(self.generate_usage_table(data.pitch_usage_right, batter_side="Right"))

            elements.extend(self.generate_two_column_layout(left_elements, right_elements))
        else:
            # If no break map, add usage tables in single column
            if data.pitch_usage_left is not None:
                elements.extend(self.generate_usage_table(data.pitch_usage_left, batter_side="Left"))
            if data.pitch_usage_right is not None:
                elements.extend(self.generate_usage_table(data.pitch_usage_right, batter_side="Right"))

        # Add pitch stats table
        if data.pitch_stats is not None:
            elements.extend(self.generate_pitcher_stats_table(data.pitch_stats))
        '''
        if (io.path.exists(io.path.join(STORAGE_SCHOOLS, self.current_user.school.slug, 'assets', 'custom_pitcher_report.py'))):
            try:
                print(f"[PDF] Generating custom pitcher report")
            except Exception as e:
                print(f"[PDF] Error generating custom pitcher report: {str(e)}")
                raise
        '''
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

    def generate_data_table(self, table: StatTable[Any] | None, title: str, available_width: float | None = None) -> list[Any]:
        """
        Render a StatTable as a titled table.

        Args:
            table: rows + column spec; formatting is declared on table.columns
            title: Section heading above the table
            available_width: Total table width in points; defaults to the full frame

        Returns:
            List of document elements containing the table
        """
        elements: list[Any] = []

        if table is None or not table:
            return elements

        if available_width is None:
            available_width = self.PAGE_W - 2 * self.MARGIN

        elements.append(Paragraph(title, self.styles["section_header"]))

        table_data = table.to_reportlab_rows()

        data_table = Table(table_data, colWidths=[available_width / len(table.columns)] * len(table.columns))
        data_table.setStyle(TableStyle([
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
        ]))

        elements.append(data_table)
        elements.append(Spacer(1, 0.05 * inch))

        return elements

    def generate_hitter_report(self, data: dict[str, Any], output_path: str) -> str:
        """
        Generate a complete hitter report PDF covering a date range.

        Mirrors generate_pitcher_report, but the header subtitle carries a date range
        rather than a single game, since a hitting report is built from every archived
        game in the selected window.

        Args:
            data: Dictionary containing report data with keys:
                  - hitter_name: str
                  - hitter_id: str
                  - date_range: str (e.g. "02/01/2026 - 05/31/2026")
                  - team: str
                  - games: int (number of games in range)
                  - summary: dict of slash-line / batted-ball stats
                  - discipline_table: pandas DataFrame of plate discipline by pitch type
                  - batted_ball_table: pandas DataFrame of batted-ball profile
                  - spray_chart_left: image path (optional)
                  - spray_chart_right: image path (optional)

            output_path: Full path where PDF should be saved

        Returns:
            Path to the generated PDF
        """

        # Resolve player pfp: player photo → school logo → statline logo
        pfp_path = os.path.join(STORAGE_SCHOOLS, str(self.current_user.school_id), 'assets', 'players', str(data.get('hitter_id')), 'pfp.png')
        player_pfp = pfp_path if os.path.exists(pfp_path) else self.school_logo

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

        elements: list[Any] = []

        print(f"[PDF] Starting hitter report generation")

        games = data.get('games')
        games_label = f"{games} game{'s' if games != 1 else ''}" if games else ''

        # generate_header's positional slots were named for pitchers; the last three
        # are free-form subtitle text, reused here for the team and game count
        elements.extend(self.generate_header(
            player_pfp,
            data.get('hitter_name', 'Hitter'),
            self.school_logo,
            data.get('date_range', ''),
            data.get('team', ''),
            games_label,
            '',
            '',
            None
        ))

        if data.get('summary'):
            elements.extend(self.generate_stats_grid(data['summary']))

        # Spray charts side by side, matching the heat-map row on pitcher reports
        half_width = (self.PAGE_W - 2 * self.MARGIN - 0.2 * inch) / 2
        spray_left = data.get('spray_chart_left')
        spray_right = data.get('spray_chart_right')
        if spray_left or spray_right:
            left_els = self.add_image_section(spray_left, "vs Left-Handed Pitching", max_width_pts=half_width) if spray_left else []
            right_els = self.add_image_section(spray_right, "vs Right-Handed Pitching", max_width_pts=half_width) if spray_right else []
            elements.extend(self.generate_two_column_layout(left_els, right_els))

        elements.extend(self.generate_data_table(data.get('batted_ball_table'), "Batted Ball Profile"))
        elements.extend(self.generate_data_table(data.get('discipline_table'), "Plate Discipline"))

        try:
            for i, el in enumerate(elements):
                try:
                    el.wrap(self.PAGE_W - 2 * self.MARGIN, self.PAGE_H)
                except Exception as e:
                    print(f"Element {i} failed: {type(el).__name__} — {e}")

            pdf_file.build(elements)
            print(f"[PDF] Hitter PDF built successfully!")
            return output_path
        except Exception as e:
            print(f"Error generating hitter PDF: {str(e)}")
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

        elements: list[Any] = []
        elements.extend(self.generate_header(
            player_pfp, 'Sample Pitcher', self.school_logo,
            '01/01/2025', 'HOME', 'AWAY',
        ))

        stats = PitcherStatsTable([
            PitchTypeStat(pitch_type='Fastball', thrown_pct=50.0, velo_low=90.0, velo_avg=93.2, velo_high=96.0, ivb=14.5, hb=8.3, spin=2345.0, vaa=-4.2, haa=0.3, rel_height=6.1, rel_side=-2.1, extension=6.8, axis='08:30', zone_pct=45.6, chase_pct=32.1, csw_pct=28.4),
            PitchTypeStat(pitch_type='Slider', thrown_pct=22.2, velo_low=81.0, velo_avg=84.1, velo_high=87.0, ivb=2.1, hb=-5.6, spin=2567.0, vaa=-5.1, haa=-1.2, rel_height=6.0, rel_side=-2.0, extension=6.5, axis='02:45', zone_pct=38.2, chase_pct=41.5, csw_pct=35.2),
            PitchTypeStat(pitch_type='Curveball', thrown_pct=16.7, velo_low=74.0, velo_avg=77.5, velo_high=81.0, ivb=-8.3, hb=6.1, spin=2789.0, vaa=-6.8, haa=0.8, rel_height=5.9, rel_side=-2.2, extension=6.3, axis='12:15', zone_pct=52.1, chase_pct=35.8, csw_pct=31.6),
            PitchTypeStat(pitch_type='Changeup', thrown_pct=11.1, velo_low=82.0, velo_avg=85.0, velo_high=88.0, ivb=7.2, hb=-3.4, spin=1876.0, vaa=-4.9, haa=-0.5, rel_height=6.1, rel_side=-2.0, extension=6.7, axis='09:50', zone_pct=41.3, chase_pct=28.9, csw_pct=25.7),
        ])
        elements.extend(self.generate_pitcher_stats_table(stats))

        lhh = PitchUsageTable([
            PitchUsageStat(pitch_type='Fastball', count=24, strike_pct=65.2, first_pitch_pct=55.0, hitter_favorable_pct=52.0, pitcher_favorable_pct=62.0, two_strike_pct=58.0, whiff_pct=18.5),
            PitchUsageStat(pitch_type='Slider', count=10, strike_pct=70.1, first_pitch_pct=30.0, hitter_favorable_pct=28.0, pitcher_favorable_pct=38.0, two_strike_pct=45.0, whiff_pct=32.4),
            PitchUsageStat(pitch_type='Curveball', count=8, strike_pct=62.5, first_pitch_pct=25.0, hitter_favorable_pct=22.0, pitcher_favorable_pct=35.0, two_strike_pct=48.0, whiff_pct=28.6),
            PitchUsageStat(pitch_type='Changeup', count=5, strike_pct=60.0, first_pitch_pct=20.0, hitter_favorable_pct=18.0, pitcher_favorable_pct=28.0, two_strike_pct=35.0, whiff_pct=22.1),
        ])
        rhh = PitchUsageTable([
            PitchUsageStat(pitch_type='Fastball', count=21, strike_pct=63.8, first_pitch_pct=52.0, hitter_favorable_pct=49.0, pitcher_favorable_pct=60.0, two_strike_pct=55.0, whiff_pct=20.1),
            PitchUsageStat(pitch_type='Slider', count=10, strike_pct=68.4, first_pitch_pct=32.0, hitter_favorable_pct=30.0, pitcher_favorable_pct=40.0, two_strike_pct=43.0, whiff_pct=30.8),
            PitchUsageStat(pitch_type='Curveball', count=7, strike_pct=60.0, first_pitch_pct=23.0, hitter_favorable_pct=20.0, pitcher_favorable_pct=32.0, two_strike_pct=46.0, whiff_pct=26.4),
            PitchUsageStat(pitch_type='Changeup', count=5, strike_pct=58.2, first_pitch_pct=18.0, hitter_favorable_pct=16.0, pitcher_favorable_pct=26.0, two_strike_pct=33.0, whiff_pct=21.5),
        ])

        half_width = (self.PAGE_W - 2 * self.MARGIN - 0.2 * inch) / 2
        # Subtract the 5pt left+right cell padding from generate_two_column_layout
        usage_width = half_width - 10
        left_els = self.generate_usage_table(lhh, batter_side="Left", available_width=usage_width)
        right_els = self.generate_usage_table(rhh, batter_side="Right", available_width=usage_width)
        elements.extend(self.generate_two_column_layout(left_els, right_els))

        doc.build(elements)
        return output_path


def find_image_with_extensions(base_path: str, extensions: list[str] | None = None) -> str | None:
    """Find an image file with any of the given extensions"""
    if extensions is None:
        extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']

    for ext in extensions:
        path = base_path + ext
        if os.path.exists(path):
            return path
    return None

def image_to_base64(img: PILImage.Image) -> str:
    """Encode a PIL image as a data: URI, for embedding directly in HTML."""
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"

def merge_pdfs(id: int, pdf_folder: str, output_path: str, prefix: str = "pitcher") -> str | None:
    """
    Merge one user's reports of a single kind into a combined PDF.

    Only files named {id}_{prefix}_*.pdf are collected, so a hitter run cannot
    sweep in the pitcher PDFs sharing the folder.

    Returns the output path, or None when nothing matched -- callers use that to
    decide whether to offer a combined download at all.
    """
    from pypdf import PdfWriter

    merger = PdfWriter()
    appended = 0

    for pdf in sorted(os.listdir(pdf_folder)):
        if pdf == os.path.basename(output_path):
            continue

        pdf_path = os.path.join(pdf_folder, pdf)
        if os.path.exists(pdf_path) and pdf_path.endswith('.pdf') and pdf.startswith(f"{id}_{prefix}_"):
            merger.append(pdf_path)
            appended += 1

    # An empty writer writes a perfectly valid zero-page PDF, so the count has to
    # be tracked -- checking the file exists afterwards would always say yes.
    if appended == 0:
        merger.close()
        print(f"No {prefix} PDFs found to merge for user {id}")
        return None

    merger.write(output_path)
    merger.close()
    print(f"Merged PDF created: {os.path.basename(output_path)}")
    return output_path

