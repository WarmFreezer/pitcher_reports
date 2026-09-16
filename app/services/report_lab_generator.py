import os
import base64
from datetime import datetime
from typing import Any

import pandas as pd
from PIL import Image as PILImage
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle,
    Image, Frame, PageTemplate, BaseDocTemplate, KeepInFrame,
    NextPageTemplate, KeepTogether,
)

from app.services.custom_report_loader import load_custom_module
from app.services.pitch_stats import (
    PitcherReportRequest,
    PitcherStatsTable,
    PitchTypeStat,
    PitchUsageStat,
    PitchUsageTable,
    PitchByPitchReport,
)
from app.services.hitter_stats import HitterReportRequest, HitterPitchByPitchAtBat, HitterPitchByPitchReport
from app.services.catcher_stats import CatcherReportRequest
from app.services.stat_table import StatTable
from .branding_loader import BrandingLoader

STORAGE_SCHOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'storage', 'schools')
STATIC_RESOURCES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'static', 'resources')

class PDF_Generator:
    PAGE_W, PAGE_H = letter
    MARGIN = 0.65 * inch
    IMG_WIDTH = 2.5 * inch
    FOOTER_HEIGHT = 0.45 * inch
    # Reserved at the top of every page after the first for _draw_running_header --
    # page 1 already carries the full header (photo/name/logo) from generate_header.
    HEADER_HEIGHT = 0.3 * inch
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

    def __init__(self, school_id: int, branding: dict[str, Any], ink_mode: str = 'full_color') -> None:
        self.school_id = school_id
        # 'full_color' (default): branded fills on report/table headers, as today.
        # 'light_ink': those same headers drop their color fill entirely and use a
        # plain thin rule instead -- less toner than even a substituted gray fill.
        self.ink_mode = ink_mode

        # Always resolve logo from local storage; fall back to the app icon if not yet uploaded
        logo_path = os.path.join(STORAGE_SCHOOLS, str(school_id), 'assets', 'logo.png')
        self.school_logo = logo_path if os.path.exists(logo_path) else os.path.join(STATIC_RESOURCES, 'statline-logo.png')

        self.primary_color = colors.HexColor(branding['colors']['primary'])
        self.secondary_color = colors.HexColor(branding['colors']['secondary'])
        self.tertiary_color = colors.HexColor(branding['colors']['tertiary'])
        self.accent_color = colors.HexColor(branding['colors']['accent'])
        self.text_color = self.primary_color
        self.dark_color = colors.HexColor(branding['colors'].get('dark', '#000000'))
        self.light_color = colors.HexColor(branding['colors'].get('light', '#FFFFFF'))
        footer_text = branding.get('report_settings', {}).get('footer_text', '')
        school_name = branding.get('school', {}).get('name', '')
        try:
            self.footer_text = footer_text.format(school_name=school_name)
        except (KeyError, IndexError):
            # A school-authored custom footer_text with its own literal {braces}
            # (not the {school_name} placeholder) -- show it as written.
            self.footer_text = footer_text

        # The masthead title/subtitle are normally white/secondary-on-tertiary-fill;
        # in light-ink mode that fill is dropped, so they need a color that's
        # actually visible against the bare page instead.
        title_color = self.dark_color if self.ink_mode == 'light_ink' else self.WHITE
        subtitle_color = self.dark_color if self.ink_mode == 'light_ink' else self.secondary_color

        self.styles = {
            "title": ParagraphStyle(
                "ReportTitle",
                fontSize=22, textColor=title_color,
                fontName="Helvetica-Bold",
                alignment=TA_LEFT, leading=26,
            ),
            "subtitle": ParagraphStyle(
                "ReportSubtitle",
                fontSize=11, textColor=subtitle_color,
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

    def _header_fill_commands(self, fill_color: Any, row_start: tuple[int, int] = (0, 0), row_end: tuple[int, int] = (-1, 0)) -> list[tuple[Any, ...]]:
        """TableStyle commands for a header/section-bar row: a colored fill with
        white text in full-color mode, or -- to save ink -- no fill at all, dark
        text, and a plain thin rule underneath as the section separator instead."""
        if self.ink_mode == 'light_ink':
            return [
                ('TEXTCOLOR', row_start, row_end, self.dark_color),
                ('LINEBELOW', row_start, row_end, 1, self.dark_color),
            ]
        return [
            ('BACKGROUND', row_start, row_end, fill_color),
            ('TEXTCOLOR', row_start, row_end, self.WHITE),
        ]

    def generate_header(self, player_pfp: str, pitcher_name: str, school_logo: str, game_date: str, home_team: str, away_team: str, pitcher_height: str = '', pitcher_weight: str = '', age: int | None = None, matchup_separator: str = '@') -> list[Any]:
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
            matchup_separator: Text between home_team and away_team -- '@' only
                reads correctly for a true single away game (away @ home); pass
                'vs' or similar for an aggregated range where the two aren't a
                real single-game home/away pair (see report_lab_generator.py TODO)

        Returns:
            List of document elements for the header
        """
        elements: list[Any] = []

        # Create center column content with title and subtitle stacked vertically
        matchup = f"{home_team} {matchup_separator} {away_team}" if home_team and away_team else (home_team or away_team)
        subtitle = ' | '.join(part for part in (game_date, matchup) if part)
        center_content = [
            Paragraph(f"<b>{pitcher_name}</b>", self.styles["title"]),
            Spacer(1, 0.05 * inch),
            Paragraph(subtitle, self.styles["subtitle"]),
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
        header_style: list[tuple[Any, ...]] = [
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
        ]
        if self.ink_mode == 'light_ink':
            header_style.append(('LINEBELOW', (0, 0), (-1, 0), 1, self.dark_color))
        else:
            header_style.append(('BACKGROUND', (0, 0), (-1, -1), self.tertiary_color))
            header_style.append(('TEXTCOLOR', (0, 0), (-1, -1), self.WHITE))
            header_style.append(('LINEBELOW', (0, 0), (-1, 0), 4, self.secondary_color))
        header_table.setStyle(TableStyle(header_style))
        header_table.spaceAfter = 0
        header_table.spaceBefore = 0

        elements.append(header_table)
        elements.append(Spacer(1, 0.05 * inch))
        
        return elements

    def _draw_custom_footer(self, canvas: Any, doc: Any) -> None:
        """
        Page decoration for the school's custom report section: draws the
        school's copyright notice above the Stat-Line.app copyright, both
        centered in the space FOOTER_HEIGHT reserves at the bottom of the page.
        """
        canvas.saveState()

        width = self.PAGE_W - 2 * self.MARGIN

        stat_line_notice = Paragraph(
            f"© {datetime.now().year} Stat-Line.app. All rights reserved.",
            self.styles["footer"],
        )
        _, stat_line_h = stat_line_notice.wrap(width, self.FOOTER_HEIGHT)
        stat_line_notice.drawOn(canvas, self.MARGIN, 0.15 * inch)

        if self.footer_text:
            school_notice = Paragraph(self.footer_text, self.styles["footer"])
            _, school_h = school_notice.wrap(width, self.FOOTER_HEIGHT)
            school_notice.drawOn(canvas, self.MARGIN, 0.15 * inch + stat_line_h)

        canvas.restoreState()

    def _draw_running_header(self, canvas: Any, doc: Any) -> None:
        """
        Slim repeating header, for the 'continuation' page template only.

        Any page that opens with its own full header (photo/name/logo) --
        page 1, and the first page of the school's custom report section,
        both via generate_header() -- uses the 'header' template instead,
        which reserves no HEADER_HEIGHT band at all, so that header sits
        flush at the top with no gap above it (see generate_pitcher_report/
        generate_hitter_report's NextPageTemplate switching). This one is
        for everything else: a table or image section that overflows onto a
        later page has nothing above it identifying whose report it is --
        this fills that gap with a single line (set as self._page_header_text
        by the report generator before doc.build()) plus a rule, in the space
        HEADER_HEIGHT reserves at the top of the 'continuation' frame.
        """
        text = getattr(self, '_page_header_text', '')
        if not text:
            return

        canvas.saveState()
        width = self.PAGE_W - 2 * self.MARGIN
        top = self.PAGE_H - self.HEADER_HEIGHT

        header_line = Paragraph(text, self.styles["footer"])
        _, h = header_line.wrap(width, self.HEADER_HEIGHT)
        header_line.drawOn(canvas, self.MARGIN, top + (self.HEADER_HEIGHT - h) / 2)

        canvas.setStrokeColor(self.secondary_color)
        canvas.setLineWidth(1)
        canvas.line(self.MARGIN, top, self.PAGE_W - self.MARGIN, top)

        canvas.restoreState()

    def _draw_page_decorations(self, canvas: Any, doc: Any) -> None:
        """Combined onPage callback for the 'continuation' template: running header + footer."""
        self._draw_running_header(canvas, doc)
        self._draw_custom_footer(canvas, doc)

    def generate_pitcher_stats_table(self, stats: PitcherStatsTable) -> list[Any]:
        """Render a pitcher's per-pitch-type stats table. Formatting comes from PitcherStatsTable.columns."""
        table_data = stats.to_reportlab_rows()

        # Create table
        col_widths = [(self.PAGE_W - 2 * self.MARGIN) / len(stats.columns)]
        stats_table = Table(table_data, colWidths=col_widths, repeatRows=1)

        # Style the table
        table_style = [
            *self._header_fill_commands(self.tertiary_color),
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

        # KeepTogether so the section header never gets orphaned at the bottom of
        # a page while the table it labels starts on the next one.
        return [
            KeepTogether([Paragraph("Pitch Statistics", self.styles["section_header"]), stats_table]),
            Spacer(1, 0.05 * inch),
        ]

    def generate_usage_table(self, usage: PitchUsageTable, batter_side: str = "Right", available_width: float | None = None) -> list[Any]:
        """Render a pitch-usage-by-count table for one batter side. Formatting comes from PitchUsageTable.columns."""
        table_data = usage.to_reportlab_rows()

        # Create table with adjusted column widths
        if available_width is None:
            available_width = (self.PAGE_W - 2 * self.MARGIN) / 2
        col_widths = available_width / len(usage.columns)
        usage_table = Table(table_data, colWidths=col_widths, repeatRows=1)

        # Style the table
        table_style = [
            *self._header_fill_commands(self.tertiary_color),
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

        # No KeepTogether here (unlike generate_data_table etc.) -- this table's
        # elements are sometimes handed to generate_two_column_layout, whose
        # KeepInFrame draws its content directly rather than through a real
        # Frame's split-aware layout, and KeepTogether relies on exactly that
        # (it reports a deliberately oversized height to force a split, which
        # KeepInFrame can't honor and crashes on with "no attribute 'draw'").
        return [
            Paragraph(f"Pitch Usage vs {batter_side}-Handed Batters", self.styles["section_header"]),
            usage_table,
            Spacer(1, 0.05 * inch),
        ]

    def generate_stats_grid(self, stats_data: dict[str, Any], title: str = "Key Statistics") -> list[Any]:
        """
        Generate a grid of key statistical boxes.

        Args:
            stats_data: Dictionary with stat names as keys and values as values
                       Example: {"Avg Velocity": "94.2", "Spin Rate": "2456", ...}
            title: Section heading above the grid

        Returns:
            List of document elements containing the stats grid
        """
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
                    # A list cell is stacked flowables to reportlab, not literal text --
                    # plain strings here blow up Table.wrapOn() once building for real.
                    row.append([Paragraph("", self.styles["stat_value"]), Paragraph("", self.styles["stat_label"])])
            grid_data.append(row)
        
        # Create table for stats grid
        col_width = (self.PAGE_W - 2 * self.MARGIN) / 4
        stats_grid_table = Table(grid_data, colWidths=[col_width] * 4)
        
        # Light tiles with dark text: accent is a saturated brand colour, and the
        # tertiary-on-accent pairing it replaced was unreadable on the default palette.
        # In light-ink mode, drop the tile fill entirely and rely on the grid lines.
        grid_style = [
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, self.dark_color if self.ink_mode == 'light_ink' else self.accent_color),
        ]
        if self.ink_mode != 'light_ink':
            grid_style.append(('BACKGROUND', (0, 0), (-1, -1), self.light_color))
        stats_grid_table.setStyle(TableStyle(grid_style))

        return [
            KeepTogether([Paragraph(title, self.styles["section_header"]), stats_grid_table]),
            Spacer(1, 0.05 * inch),
        ]

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
            # No KeepTogether here (unlike generate_data_table etc.) -- this is
            # sometimes handed to generate_two_column_layout, whose KeepInFrame
            # draws its content directly rather than through a real Frame's
            # split-aware layout, and KeepTogether relies on exactly that (it
            # reports a deliberately oversized height to force a split, which
            # KeepInFrame can't honor and crashes on with "no attribute 'draw'").
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
        
        summary_style = [
            *self._header_fill_commands(self.accent_color),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]
        # Full-saturation zebra stripe -- heavier than the pale light_color stripe
        # used elsewhere, so it's the one other zebra this mode also drops.
        if self.ink_mode != 'light_ink':
            summary_style.append(('ROWBACKGROUNDS', (0, 1), (-1, -1), [self.WHITE, self.tertiary_color]))
        summary_table.setStyle(TableStyle(summary_style))
        
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

        # Bounded by the smallest frame this can land on (the 'custom' template,
        # which reserves both HEADER_HEIGHT and FOOTER_HEIGHT) rather than the raw
        # page height -- self.PAGE_H here is taller than any actual frame now that
        # HEADER_HEIGHT is reserved on every page, which made KeepInFrame promise a
        # size no frame could actually satisfy and crash the whole build.
        max_height = self.PAGE_H - self.HEADER_HEIGHT - self.FOOTER_HEIGHT

        # Wrap elements in KeepInFrame to constrain width for table cells
        left_frame = KeepInFrame(col_width, max_height, left_elements, hAlign='LEFT')
        right_frame = KeepInFrame(col_width, max_height, right_elements, hAlign='LEFT')
        
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
        pfp_path = os.path.join(STORAGE_SCHOOLS, str(self.school_id), 'assets', 'players', str(data.pitcher_id), 'pfp.png')
        player_pfp = pfp_path if os.path.exists(pfp_path) else self.school_logo
        # Stashed on self so a school's custom_pitcher_report.py can read gen.player_pfp,
        # matching the already-public gen.school_logo it also relies on.
        self.player_pfp = player_pfp
        # Read by _draw_running_header on every page after the first, so a section
        # that overflows past page 1 still carries its own context.
        self._page_header_text = f"{data.pitcher_name}  |  {data.date}  |  {data.home_team} {data.matchup_separator} {data.away_team}"

        # 'header': used for any page that opens with its own full generate_header()
        # call (page 1, and the custom report section's own first page) -- no
        # HEADER_HEIGHT reservation, so that header sits flush at the top with no
        # gap above it. Only FOOTER_HEIGHT is reserved, for the copyright footer.
        header_frame = Frame(
            self.MARGIN,
            self.FOOTER_HEIGHT,
            self.PAGE_W - 2 * self.MARGIN,
            self.PAGE_H - self.FOOTER_HEIGHT,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )

        # 'continuation': used for every other page -- one that picks up mid-section
        # with no header of its own. Also reserves HEADER_HEIGHT at the top for
        # _draw_running_header, so a table/image that overflows this far still
        # carries some context for whose report it is.
        continuation_frame = Frame(
            self.MARGIN,
            self.FOOTER_HEIGHT,
            self.PAGE_W - 2 * self.MARGIN,
            self.PAGE_H - self.FOOTER_HEIGHT - self.HEADER_HEIGHT,
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
        pdf_file.addPageTemplates([
            # 'header' first so it's the default template page 1 starts on.
            PageTemplate(id='header', frames=[header_frame], onPage=self._draw_custom_footer),
            PageTemplate(id='continuation', frames=[continuation_frame], onPage=self._draw_page_decorations),
        ])

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
            data.matchup_separator,
        ))
        # Anything that overflows past this page has no header of its own --
        # switch to the reserved-band template so it gets the running header.
        elements.append(NextPageTemplate('continuation'))
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

        # The custom report's own page break + header (school-defined, tier 3) has
        # to come before the custom stats tables below, so those tables land on the
        # new page it starts rather than trailing the standard content above.
        try:
            custom_module = load_custom_module(self.school_id, 'custom_pitcher_report.py')
            if custom_module is not None:
                print(f"[PDF] Generating custom pitcher report")
                # The custom script's own PageBreak() lands on this switch -- 'header'
                # so its generate_header() call sits flush at the top with no gap,
                # same as page 1. Anything the custom script/tables below add that
                # overflows past that page switches back to 'continuation'.
                elements.append(NextPageTemplate('header'))
                elements.extend(self._load_custom_elements(custom_module, data))
                elements.append(NextPageTemplate('continuation'))
        except Exception as e:
            # A school's custom script is theirs to break -- don't let it take
            # down the rest of an otherwise-normal report.
            print(f"[PDF] Error generating custom pitcher report: {str(e)}")

        # Add custom stats grid (school-defined, tier 3) -- tiles like the hitter
        # report's Key Statistics, not a name/value row per stat
        if data.custom_stats:
            custom_stats_dict = {row.name: row.value for row in data.custom_stats}
            elements.extend(self.generate_stats_grid(custom_stats_dict, title="Custom Stats"))

        # Add custom pitch-type stats tables (school-defined, tier 3)
        if data.custom_pitch_type_stats:
            for custom_pitch_table in data.custom_pitch_type_stats:
                elements.extend(self.generate_data_table(custom_pitch_table, custom_pitch_table.title or "Custom Pitch Type Stats"))

        # Build PDF
        try:
            for i, el in enumerate(elements):
                # KeepTogether.wrap() needs a live canvas (set during the real build
                # below), so it always raises here regardless of whether its content
                # is fine -- skip it rather than log a false "failed" for every
                # section header+table pairing.
                if isinstance(el, KeepTogether):
                    continue
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

    def _load_custom_elements(self, custom_module: Any, data: PitcherReportRequest) -> list[Any]:
        get_elements = getattr(custom_module, "get_elements", None)
        if get_elements is None:
            raise AttributeError(f"Module {custom_module.__name__} does not have a 'get_elements' function")

        return get_elements(self, data) or []

    def generate_pitch_by_pitch_report(self, data: PitchByPitchReport, output_path: str) -> str:
        """
        Generate the simplified pitch-by-pitch PDF: a plain header (pitcher, date,
        matchup) followed by every at-bat faced, each with its pitches numbered in
        the order thrown. Deliberately lighter than generate_pitcher_report -- no
        photo/logo banner, no heat maps -- since the whole point of this report is
        to trim the old raw-CSV export down to what a coach actually reads.
        """
        frame = Frame(
            self.MARGIN, self.FOOTER_HEIGHT,
            self.PAGE_W - 2 * self.MARGIN, self.PAGE_H - self.FOOTER_HEIGHT - self.HEADER_HEIGHT,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )
        self._page_header_text = '  |  '.join(part for part in (data.pitcher_name, data.date, data.matchup) if part)

        doc = BaseDocTemplate(
            output_path, pagesize=letter,
            rightMargin=self.MARGIN, leftMargin=self.MARGIN, topMargin=0, bottomMargin=0,
        )
        doc.addPageTemplates([PageTemplate(id='continuation', frames=[frame], onPage=self._draw_page_decorations)])

        title_style = ParagraphStyle(
            "PbpTitle", fontSize=18, textColor=self.dark_color,
            fontName="Helvetica-Bold", leading=22, spaceAfter=2,
        )
        subtitle_style = ParagraphStyle(
            "PbpSubtitle", fontSize=10, textColor=self.dark_color,
            fontName="Helvetica", leading=13, spaceAfter=10,
        )
        ab_heading_style = ParagraphStyle(
            "PbpAbHeading", fontSize=10, textColor=self.dark_color,
            fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4,
        )

        elements: list[Any] = [
            Paragraph(data.pitcher_name, title_style),
            Paragraph(' | '.join(part for part in (data.date, data.matchup) if part), subtitle_style),
        ]

        if not data.at_bats:
            elements.append(Paragraph("No pitches found for the selected games.", self.styles["body"]))

        available_width = self.PAGE_W - 2 * self.MARGIN
        fixed_widths = [0.4 * inch, 1.4 * inch, 0.8 * inch, 0.8 * inch]
        col_widths = fixed_widths + [available_width - sum(fixed_widths)]

        for ab in data.at_bats:
            heading_parts = [ab.inning, ab.batter_name]
            side_abbr = {'Left': 'LHH', 'Right': 'RHH'}.get(ab.batter_side)
            if side_abbr:
                heading_parts[-1] += f" ({side_abbr})"
            if ab.result:
                heading_parts.append(ab.result)
            heading = ' — '.join(part for part in heading_parts if part)

            rows = [["#", "Pitch", "Velo", "Count", "Result"]]
            for p in ab.pitches:
                velo_str = f"{p.velo:.1f}" if p.velo is not None else ""
                rows.append([str(p.number), p.pitch_type, velo_str, f"{p.balls}-{p.strikes}", p.result])

            ab_table = Table(rows, colWidths=col_widths, repeatRows=1)
            ab_table.setStyle(TableStyle([
                *self._header_fill_commands(self.tertiary_color),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [self.WHITE, self.light_color]),
            ]))

            elements.append(KeepTogether([Paragraph(heading, ab_heading_style), ab_table]))
            elements.append(Spacer(1, 0.05 * inch))

        doc.build(elements)
        return output_path

    def generate_hitter_pitch_by_pitch_report(self, data: HitterPitchByPitchReport, output_path: str) -> str:
        """
        Generate the simplified pitch-by-pitch PDF for a hitter: a plain header
        (hitter, date range) followed by every at-bat, each with the pitches seen
        numbered in the order thrown. Mirrors generate_pitch_by_pitch_report, with
        the opponent per at-bat shown as the pitcher faced rather than a batter.
        """
        # A small gap above FOOTER_HEIGHT so a page-ending table doesn't sit flush
        # against the copyright footer.
        footer_gap = 0.15 * inch
        frame = Frame(
            self.MARGIN, self.FOOTER_HEIGHT + footer_gap,
            self.PAGE_W - 2 * self.MARGIN, self.PAGE_H - self.FOOTER_HEIGHT - self.HEADER_HEIGHT - footer_gap,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )
        self._page_header_text = '  |  '.join(part for part in (data.hitter_name, data.date_range) if part)

        doc = BaseDocTemplate(
            output_path, pagesize=letter,
            rightMargin=self.MARGIN, leftMargin=self.MARGIN, topMargin=0, bottomMargin=0,
        )
        doc.addPageTemplates([PageTemplate(id='continuation', frames=[frame], onPage=self._draw_page_decorations)])

        title_style = ParagraphStyle(
            "PbpTitle", fontSize=18, textColor=self.dark_color,
            fontName="Helvetica-Bold", leading=22, spaceAfter=2,
        )
        subtitle_style = ParagraphStyle(
            "PbpSubtitle", fontSize=10, textColor=self.dark_color,
            fontName="Helvetica", leading=13, spaceAfter=10,
        )
        ab_heading_style = ParagraphStyle(
            "PbpAbHeading", fontSize=10, textColor=self.dark_color,
            fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4,
        )

        elements: list[Any] = [
            Paragraph(data.hitter_name, title_style),
            Paragraph(data.date_range, subtitle_style),
        ]

        if not data.at_bats:
            elements.append(Paragraph("No pitches found for the selected range.", self.styles["body"]))

        available_width = self.PAGE_W - 2 * self.MARGIN
        gutter = 0.3 * inch
        half_width = (available_width - gutter) / 2
        fixed_widths = [0.3 * inch, 0.9 * inch, 0.55 * inch, 0.55 * inch]
        inner_col_widths = fixed_widths + [half_width - sum(fixed_widths)]
        chart_w = min(half_width, 2.0 * inch)

        def truncate_to_width(text: str, font_name: str, font_size: float, max_width: float) -> str:
            """Hard-cap a string to one line at max_width, since a wrapped second
            line would push that cell's chart+table down and throw off alignment
            with its neighbor in the pair row."""
            if stringWidth(text, font_name, font_size) <= max_width:
                return text
            ellipsis = '…'
            while text and stringWidth(text + ellipsis, font_name, font_size) > max_width:
                text = text[:-1]
            return (text + ellipsis) if text else ellipsis

        def ab_cell(ab: HitterPitchByPitchAtBat) -> list[Any]:
            heading_parts = [ab.inning, ab.pitcher_name]
            throws_abbr = {'Left': 'LHP', 'Right': 'RHP'}.get(ab.pitcher_throws)
            if throws_abbr:
                heading_parts[-1] += f" ({throws_abbr})"
            if ab.result:
                heading_parts.append(ab.result)
            heading = ' — '.join(part for part in heading_parts if part)
            heading = truncate_to_width(heading, ab_heading_style.fontName, ab_heading_style.fontSize, half_width)

            rows = [["#", "Pitch", "Velo", "Count", "Result"]]
            for p in ab.pitches:
                velo_str = f"{p.velo:.1f}" if p.velo is not None else ""
                rows.append([str(p.number), p.pitch_type, velo_str, f"{p.balls}-{p.strikes}", p.result])

            ab_table = Table(rows, colWidths=inner_col_widths, repeatRows=1)
            ab_table.setStyle(TableStyle([
                *self._header_fill_commands(self.tertiary_color),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [self.WHITE, self.light_color]),
            ]))

            cell: list[Any] = [Paragraph(heading, ab_heading_style)]
            if ab.chart_path and os.path.exists(ab.chart_path):
                chart_img = PILImage.open(ab.chart_path)
                chart_h = chart_w * chart_img.height / chart_img.width
                chart_holder = Table([[Image(ab.chart_path, width=chart_w, height=chart_h)]], colWidths=[half_width])
                chart_holder.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ]))
                cell.append(chart_holder)
            cell.append(ab_table)
            return cell

        # Two ABs per line, chart directly above its own table, so a coach reads
        # the chart and the pitch list together instead of flipping pages between
        # them -- a single-row Table per pair keeps both cells on the same page
        # (ReportLab pushes the whole row to the next page rather than splitting
        # a cell's chart away from its table).
        for i in range(0, len(data.at_bats), 2):
            pair = data.at_bats[i:i + 2]
            # The gutter is its own middle column rather than cell padding on the
            # second AB -- padding would shrink that cell's usable width relative
            # to the first, making its heading/table wrap differently and throwing
            # off the two cells' alignment.
            row = [ab_cell(pair[0]), '', ab_cell(pair[1]) if len(pair) > 1 else '']
            pair_table = Table([row], colWidths=[half_width, gutter, half_width])
            pair_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            elements.append(pair_table)
            elements.append(Spacer(1, 0.15 * inch))

        doc.build(elements)
        return output_path

    def generate_data_table(self, table: StatTable[Any] | None, title: str, available_width: float | None = None, col_widths: list[float] | None = None) -> list[Any]:
        """
        Render a StatTable as a titled table.

        Args:
            table: rows + column spec; formatting is declared on table.columns
            title: Section heading above the table
            available_width: Total table width in points; defaults to the full frame.
                Ignored once column widths are resolved (see col_widths).
            col_widths: Explicit per-column widths in points, overriding the default
                even split of available_width. Falls back to table.col_widths (set by
                the table's producer, e.g. a school's custom_pitcher_report.py) when
                not given here.

        Returns:
            List of document elements containing the table
        """
        if table is None or not table:
            return []

        if available_width is None:
            available_width = self.PAGE_W - 2 * self.MARGIN

        table_data = table.to_reportlab_rows()

        # Column count comes from the rendered header row, not table.columns --
        # CustomPitchTypeStatsTable derives its headers at runtime from stat_names
        # and leaves the static `columns` classvar empty.
        col_count = len(table_data[0]) if table_data else len(table.columns)

        widths = col_widths if col_widths is not None else table.col_widths
        if widths is not None and len(widths) != col_count:
            print(f"[PDF] col_widths has {len(widths)} entries but '{title}' has {col_count} columns -- using an even split instead")
            widths = None
        if widths is None:
            widths = [available_width / col_count] * col_count

        data_table = Table(table_data, colWidths=widths, repeatRows=1)
        data_table.setStyle(TableStyle([
            *self._header_fill_commands(self.tertiary_color),
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

        return [
            KeepTogether([Paragraph(title, self.styles["section_header"]), data_table]),
            Spacer(1, 0.05 * inch),
        ]

    def generate_hitter_report(self, data: HitterReportRequest, output_path: str) -> str:
        """
        Generate a complete hitter report PDF covering a date range.

        Mirrors generate_pitcher_report, but the header subtitle carries a date range
        rather than a single game, since a hitting report is built from every archived
        game in the selected window.

        Args:
            data: Everything needed to build one hitter's report -- see HitterReportRequest.
            output_path: Full path where PDF should be saved

        Returns:
            Path to the generated PDF
        """

        # Resolve player pfp: player photo → school logo → statline logo
        pfp_path = os.path.join(STORAGE_SCHOOLS, str(self.school_id), 'assets', 'players', str(data.hitter_id), 'pfp.png')
        player_pfp = pfp_path if os.path.exists(pfp_path) else self.school_logo
        # Stashed on self so a school's custom_hitter_report.py can read gen.player_pfp,
        # matching the already-public gen.school_logo it also relies on.
        self.player_pfp = player_pfp
        # Read by _draw_running_header on every page after the first, so a section
        # that overflows past page 1 still carries its own context.
        games_label = f"{data.games} game{'s' if data.games != 1 else ''}" if data.games else ''
        header_bits = [data.hitter_name, data.date_range, data.team, games_label]
        self._page_header_text = '  |  '.join(bit for bit in header_bits if bit)

        # 'header': used for any page that opens with its own full generate_header()
        # call (page 1, and the custom report section's own first page) -- no
        # HEADER_HEIGHT reservation, so that header sits flush at the top with no
        # gap above it. Only FOOTER_HEIGHT is reserved, for the copyright footer.
        header_frame = Frame(
            self.MARGIN,
            self.FOOTER_HEIGHT,
            self.PAGE_W - 2 * self.MARGIN,
            self.PAGE_H - self.FOOTER_HEIGHT,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )

        # 'continuation': used for every other page -- one that picks up mid-section
        # with no header of its own. Also reserves HEADER_HEIGHT at the top for
        # _draw_running_header, so a table/image that overflows this far still
        # carries some context for whose report it is.
        continuation_frame = Frame(
            self.MARGIN,
            self.FOOTER_HEIGHT,
            self.PAGE_W - 2 * self.MARGIN,
            self.PAGE_H - self.FOOTER_HEIGHT - self.HEADER_HEIGHT,
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
        pdf_file.addPageTemplates([
            # 'header' first so it's the default template page 1 starts on.
            PageTemplate(id='header', frames=[header_frame], onPage=self._draw_custom_footer),
            PageTemplate(id='continuation', frames=[continuation_frame], onPage=self._draw_page_decorations),
        ])

        elements: list[Any] = []

        print(f"[PDF] Starting hitter report generation")

        games = data.games
        games_label = f"{games} game{'s' if games != 1 else ''}" if games else ''

        # generate_header's positional slots were named for pitchers; the last three
        # are free-form subtitle text, reused here for the team and game count. Team
        # and game count aren't a home/away pair, so join them like the running
        # header below does rather than with '@'.
        elements.extend(self.generate_header(
            player_pfp,
            data.hitter_name,
            self.school_logo,
            data.date_range,
            data.team,
            games_label,
            '',
            '',
            None,
            '|',
        ))
        # Anything that overflows past this page has no header of its own --
        # switch to the reserved-band template so it gets the running header.
        elements.append(NextPageTemplate('continuation'))

        if data.summary:
            elements.extend(self.generate_stats_grid(data.summary))

        # Spray charts side by side, matching the heat-map row on pitcher reports
        half_width = (self.PAGE_W - 2 * self.MARGIN - 0.2 * inch) / 2
        if data.spray_chart_left or data.spray_chart_right:
            left_els = self.add_image_section(data.spray_chart_left, "vs Left-Handed Pitching", max_width_pts=half_width) if data.spray_chart_left else []
            right_els = self.add_image_section(data.spray_chart_right, "vs Right-Handed Pitching", max_width_pts=half_width) if data.spray_chart_right else []
            elements.extend(self.generate_two_column_layout(left_els, right_els))

        elements.extend(self.generate_data_table(data.batted_ball_table, "Batted Ball Profile"))
        elements.extend(self.generate_data_table(data.discipline_table, "Plate Discipline"))

        # The custom report's own page break + header (school-defined, tier 3) has
        # to come before the custom stats/charts/tables below, so those land on the
        # new page it starts rather than trailing the standard content above.
        try:
            custom_module = load_custom_module(self.school_id, 'custom_hitter_report.py')
            if custom_module is not None:
                print(f"[PDF] Generating custom hitter report")
                # The custom script's own PageBreak() lands on this switch -- 'header'
                # so its generate_header() call sits flush at the top with no gap,
                # same as page 1. Anything the custom script/tables below add that
                # overflows past that page switches back to 'continuation'.
                elements.append(NextPageTemplate('header'))
                elements.extend(self._load_custom_hitter_elements(custom_module, data))
                elements.append(NextPageTemplate('continuation'))
        except Exception as e:
            # A school's custom script is theirs to break -- don't let it take
            # down the rest of an otherwise-normal report.
            print(f"[PDF] Error generating custom hitter report: {str(e)}")

        # Add custom stats grid (school-defined, tier 3) -- tiles like the
        # pitcher report's Custom Stats
        if data.custom_stats:
            custom_stats_dict = {row.name: row.value for row in data.custom_stats}
            elements.extend(self.generate_stats_grid(custom_stats_dict, title="Custom Stats"))

        # Add custom chart(s) (school-defined, tier 3) -- stacked full-width since
        # a school may return any number of them, unlike the fixed left/right spray pair
        if data.custom_chart_paths:
            for title, path in data.custom_chart_paths:
                elements.extend(self.add_image_section(path, title))

        # Add custom hit-type stats tables (school-defined, tier 3)
        if data.custom_hit_type_stats:
            for custom_hit_table in data.custom_hit_type_stats:
                elements.extend(self.generate_data_table(custom_hit_table, custom_hit_table.title or "Custom Hit Type Stats"))

        # Add custom pitch-type stats tables (school-defined, tier 3)
        if data.custom_pitch_type_stats:
            for custom_pitch_table in data.custom_pitch_type_stats:
                elements.extend(self.generate_data_table(custom_pitch_table, custom_pitch_table.title or "Custom Pitch Type Stats"))

        try:
            for i, el in enumerate(elements):
                # KeepTogether.wrap() needs a live canvas (set during the real build
                # below), so it always raises here regardless of whether its content
                # is fine -- skip it rather than log a false "failed" for every
                # section header+table pairing.
                if isinstance(el, KeepTogether):
                    continue
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

    def _load_custom_hitter_elements(self, custom_module: Any, data: HitterReportRequest) -> list[Any]:
        get_elements = getattr(custom_module, "get_elements", None)
        if get_elements is None:
            raise AttributeError(f"Module {custom_module.__name__} does not have a 'get_elements' function")

        return get_elements(self, data) or []

    def generate_catcher_report(self, data: CatcherReportRequest, output_path: str) -> str:
        """
        Generate a complete catcher (framing/SLAA) report PDF covering a date range.

        Mirrors generate_hitter_report's shape (header + charts + one data table,
        no tier-3 custom-report hook -- there's no custom_catcher_report.py concept).
        """
        pfp_path = os.path.join(STORAGE_SCHOOLS, str(self.school_id), 'assets', 'players', str(data.catcher_id), 'pfp.png')
        player_pfp = pfp_path if os.path.exists(pfp_path) else self.school_logo

        games_label = f"{data.games} game{'s' if data.games != 1 else ''}" if data.games else ''
        header_bits = [data.catcher_name, data.date_range, data.team, games_label]
        self._page_header_text = '  |  '.join(bit for bit in header_bits if bit)

        header_frame = Frame(
            self.MARGIN, self.FOOTER_HEIGHT, self.PAGE_W - 2 * self.MARGIN, self.PAGE_H - self.FOOTER_HEIGHT,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )
        continuation_frame = Frame(
            self.MARGIN, self.FOOTER_HEIGHT, self.PAGE_W - 2 * self.MARGIN,
            self.PAGE_H - self.FOOTER_HEIGHT - self.HEADER_HEIGHT,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )

        pdf_file = BaseDocTemplate(
            output_path, pagesize=letter, rightMargin=self.MARGIN, leftMargin=self.MARGIN,
            topMargin=0, bottomMargin=0,
        )
        pdf_file.addPageTemplates([
            PageTemplate(id='header', frames=[header_frame], onPage=self._draw_custom_footer),
            PageTemplate(id='continuation', frames=[continuation_frame], onPage=self._draw_page_decorations),
        ])

        elements: list[Any] = []

        print(f"[PDF] Starting catcher report generation")

        elements.extend(self.generate_header(
            player_pfp, data.catcher_name, self.school_logo,
            data.date_range, data.team, games_label, '', '', None, '|',
        ))
        elements.append(NextPageTemplate('continuation'))

        half_width = (self.PAGE_W - 2 * self.MARGIN - 0.2 * inch) / 2
        if data.heat_map or data.pitch_location_chart:
            left_els = self.add_image_section(data.heat_map, "Framing Heat Map", max_width_pts=half_width) if data.heat_map else []
            right_els = self.add_image_section(data.pitch_location_chart, "Pitch Location", max_width_pts=half_width) if data.pitch_location_chart else []
            elements.extend(self.generate_two_column_layout(left_els, right_els))

        elements.extend(self.generate_data_table(data.framing_table, "Framing"))

        try:
            for i, el in enumerate(elements):
                if isinstance(el, KeepTogether):
                    continue
                try:
                    el.wrap(self.PAGE_W - 2 * self.MARGIN, self.PAGE_H)
                except Exception as e:
                    print(f"Element {i} failed: {type(el).__name__} — {e}")

            pdf_file.build(elements)
            print(f"[PDF] Catcher PDF built successfully!")
            return output_path
        except Exception as e:
            print(f"Error generating catcher PDF: {str(e)}")
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
            PitchTypeStat(pitch_type='Fastball', thrown_pct=50.0, velo_low=90.0, velo_avg=93.2, velo_high=96.0, ivb=14.5, hb=8.3, spin=2345.0, vaa=-4.2, haa=0.3, rel_height=6.1, rel_side=-2.1, extension=6.8, axis='08:30', zone_pct=45.6, chase_pct=32.1, csw_pct=28.4, damage_pct=18.2),
            PitchTypeStat(pitch_type='Slider', thrown_pct=22.2, velo_low=81.0, velo_avg=84.1, velo_high=87.0, ivb=2.1, hb=-5.6, spin=2567.0, vaa=-5.1, haa=-1.2, rel_height=6.0, rel_side=-2.0, extension=6.5, axis='02:45', zone_pct=38.2, chase_pct=41.5, csw_pct=35.2, damage_pct=9.5),
            PitchTypeStat(pitch_type='Curveball', thrown_pct=16.7, velo_low=74.0, velo_avg=77.5, velo_high=81.0, ivb=-8.3, hb=6.1, spin=2789.0, vaa=-6.8, haa=0.8, rel_height=5.9, rel_side=-2.2, extension=6.3, axis='12:15', zone_pct=52.1, chase_pct=35.8, csw_pct=31.6, damage_pct=6.7),
            PitchTypeStat(pitch_type='Changeup', thrown_pct=11.1, velo_low=82.0, velo_avg=85.0, velo_high=88.0, ivb=7.2, hb=-3.4, spin=1876.0, vaa=-4.9, haa=-0.5, rel_height=6.1, rel_side=-2.0, extension=6.7, axis='09:50', zone_pct=41.3, chase_pct=28.9, csw_pct=25.7, damage_pct=13.4),
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
    sweep in the pitcher PDFs sharing the folder. Also excludes the standalone
    pitch-by-pitch companion PDF ({id}_hitter_{batter_id}_pitch_by_pitch.pdf) --
    it shares the {id}_hitter_ prefix but is a separate optional download, not
    part of the standard per-hitter report.

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
        if (os.path.exists(pdf_path) and pdf_path.endswith('.pdf')
                and pdf.startswith(f"{id}_{prefix}_")
                and not pdf.endswith('_pitch_by_pitch.pdf')):
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

