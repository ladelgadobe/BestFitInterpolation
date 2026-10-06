"""Snapshot report model and single HTML source for preview and PDF."""
from dataclasses import dataclass,field
import html
import re
import os
from .theme import COLORS,clean_display_name


@dataclass
class ReportFigure:
    caption: str
    image_html: str


@dataclass
class ReportTable:
    headers: tuple
    rows: tuple

    def html(self):
        def esc(value):
            if isinstance(value,float): value="{:.6g}".format(value)
            elif isinstance(value,(tuple,list)):
                return "("+", ".join(esc(item) for item in value)+")"
            return html.escape(str(value))
        return "<table><thead><tr>"+"".join("<th>"+esc(v)+"</th>" for v in self.headers)+"</tr></thead><tbody>"+"".join("<tr>"+"".join("<td>"+esc(v)+"</td>" for v in row)+"</tr>" for row in self.rows)+"</tbody></table>"


@dataclass
class ReportSection:
    key: str
    title: str
    body: str = ""
    mandatory: bool = False
    enabled: bool = True
    figures: list = field(default_factory=list)
    tables: list = field(default_factory=list)


@dataclass
class ReportState:
    title: str = "Best Fit Interpolator Technical Report"
    sections: list = field(default_factory=list)
    assets: list = field(default_factory=list)
    study_name: str = ""
    author: str = ""
    notes: str = ""


def report_html(state):
    c=COLORS; esc=html.escape
    css="""body { font-family: Arial; font-size: 10pt; color: %(text_primary)s; }
    h1 { font-size: 19pt; color: %(primary_dark)s; }
    h2 { font-size: 13pt; color: %(primary)s; margin-top: 18px; border-bottom: 1px solid %(border)s; }
    p { margin: 5px 0; line-height: 1.3; }
    table { border-collapse: collapse; width: 100%%; margin: 8px 0; }
    th { background: #e5f2f5; color: %(primary_dark)s; }
    th,td { border: 1px solid %(border)s; padding: 5px; font-size: 8pt; }
    .figure-block { page-break-inside: avoid; text-align:center; margin: 12px 0; }
    .figure-caption { font-size: 9pt; color: %(text_secondary)s; }
    img.report-figure { width: 590px; } img.decision-tree-figure { width: 650px; }
    """ % c
    from pathlib import Path
    icon=Path(os.path.join(os.path.dirname(__file__),"icon.png")).as_uri()
    body="<p><img width='30' height='30' src='"+icon+"'></p><h1>"+esc(state.title)+"</h1>"
    for label,value in (("Study",state.study_name),("Author",state.author),("Notes",state.notes)):
        if value: body+="<p><b>"+label+":</b> "+esc(value)+"</p>"
    number=0
    previous = None
    for section in state.sections:
        if not section.enabled and not section.mandatory: continue
        number+=1
        # Start validation on a fresh page so its header cannot orphan its rows.
        # Its small table leaves enough space for the following comparison plot.
        validation = section.title == "Validation Results"
        large_table = any(len(table.rows)>20 for table in section.tables)
        after_validation = previous is not None and previous.title == "Validation Results"
        diagnostic_summary=section.key=='diagnostics'
        start=" style='page-break-before: always;'" if validation or large_table or diagnostic_summary or (section.figures and not after_validation) else ""
        body+="<h2{}>{}. {}</h2>".format(start,number,esc(section.title))+section.body
        body+="".join(table.html() for table in section.tables)
        body+="".join(figure.image_html for figure in section.figures)
        previous = section
    return "<html><head><style>"+css+"</style></head><body>"+body+"</body></html>"


def snapshot_framework_report(framework):
    """Capture existing content and figures once; renderers never read widgets."""
    legacy=framework._collect_legacy_report_html()
    body=legacy.split("<body>",1)[-1].split("</body>",1)[0]
    parts=re.split(r"<h2>(.*?)</h2>",body,flags=re.S)
    state=ReportState()
    for index in range(1,len(parts),2):
        title=clean_display_name(re.sub(r"^\d+\.\s*","",parts[index]))
        content=parts[index+1]
        figures=re.findall(r"<div class='figure-block'.*?</div>",content,flags=re.S)
        content=re.sub(r"<div class='figure-block'.*?</div>","",content,flags=re.S)
        # Preserve original report content; only existing figures become options.
        if content.strip(): state.sections.append(ReportSection("legacy_"+str(index),title,content,mandatory=True))
        for j,figure in enumerate(figures):
            caption=re.search(r"class='figure-caption'>(.*?)</p>",figure,flags=re.S)
            text=clean_display_name(html.unescape(caption.group(1))) if caption else title+" figure"
            if caption:
                figure=figure[:caption.start(1)]+html.escape(text)+figure[caption.end(1):]
            state.sections.append(ReportSection("figure_{}_{}".format(index,j),text,figures=[ReportFigure(text,figure)]))
    plugin=framework.plugin
    if plugin is not None:
        from qgis.core import QgsProject
        layers=QgsProject.instance().mapLayersByName(plugin.dlg.Points.currentText())
        ds=plugin.diagnostics_states.get((layers[0].id(),plugin.dlg.Points_2.currentText())) if layers else None
        if ds is not None and ds.result:
            r=ds.result
            summary=ReportTable(("Statistic","Value"),tuple(r["summary"].items()))
            state.sections.append(ReportSection("diagnostics","Spatial diagnostics",tables=[summary]))
            table=ReportTable(("ID","Statistical votes","Statistical flag","LISA","Pseudo p","Combined class","User decision"),
                tuple((int(fid),str(r["votes"][i])+"/"+str(len(r["methods"])),bool(r["statistical"][i]),r["lisa"][i],"{:.4g}".format(r["pseudo_p"][i]),r["combined"][i],ds.decisions.get(int(fid),"Undecided")) for i,fid in enumerate(ds.ids)))
            state.sections.append(ReportSection("outliers","Outlier diagnostics",tables=[table]))
            g=r["global_moran"]
            state.sections.append(ReportSection("global_moran","Global Moran (diagnostic only)",tables=[ReportTable(("Item","Value"),tuple(g.items()))]))
            from matplotlib.figure import Figure
            from .diagnostics_plot import draw_diagnostics
            diagnostic_figure=Figure(figsize=(10,3))
            draw_diagnostics(diagnostic_figure,ds)
            block=framework._report_figure_block("LISA, histogram and boxplot",diagnostic_figure)
            state.sections.append(ReportSection("lisa","LISA and distributions",figures=[ReportFigure("LISA and distributions",block)]))
            state.sections.append(ReportSection("diagnostic_methodology","Diagnostic methodology",
                body="<p>Local Moran uses row-standardized weights, population second moment m2 = sum((x - mean)^2) / n, conditional randomization and unadjusted pseudo p values. HH/LL are clusters and significant HL/LH are potential spatial outliers. Thresholds and neighborhoods apply to the original finite data; exclusions affect subsequent model inputs.</p>",
                tables=[ReportTable(("Setting","Value"),tuple(ds.settings.items())+tuple(r["neighborhood"].items()))]))
        if ds is not None:
            state.sections.append(ReportSection("decisions","Analysis mask and user decisions",
                body="<p>Original observations: {}; analysis observations: {}; excluded by user: {}. The source layer remains unchanged.</p>".format(len(ds.ids),int(ds.analysis_mask.sum()),sum(v=="Exclude" for v in ds.decisions.values())),mandatory=True))
    comparison=framework.state.__dict__.get("map_comparison")
    widget=getattr(framework,"comparison_widget",None)
    if comparison is not None and comparison.include_report and widget is not None and comparison.previews:
        block=framework._report_figure_block("{} / {} / signed difference".format(comparison.method_a,comparison.method_b),widget.fig)
        table=ReportTable(("Item","Value"),tuple(comparison.statistics.items())+(("Method A",comparison.method_a),("Method B",comparison.method_b),("Palette A",comparison.palette_a),("Palette B",comparison.palette_b),("Value range A",str(comparison.value_range)),("Value range B",str(comparison.value_range_b)),("Display scale",comparison.scale or "Fit to layer"),("View extent",comparison.view_extent),("Difference raster",comparison.difference_path)))
        state.sections.append(ReportSection("map_comparison","Map comparison and signed difference",figures=[ReportFigure("Map comparison",block)],tables=[table]))
    state.assets=list(getattr(framework,"_report_image_paths",[]))
    return state


def export_report_html(state,path):
    """Export navigable, collapsible sections with embedded local figure assets."""
    import base64
    import mimetypes
    from pathlib import Path
    from urllib.parse import unquote,urlparse
    from urllib.request import url2pathname
    esc=html.escape
    sections=[section for section in state.sections if section.enabled or section.mandatory]
    def embedded(match):
        uri=html.unescape(match.group(2))
        if not uri.startswith('file:'): return match.group(0)
        source=Path(url2pathname(unquote(urlparse(uri).path)))
        data=base64.b64encode(source.read_bytes()).decode('ascii')
        mime=mimetypes.guess_type(str(source))[0] or 'image/png'
        return 'src="data:{};base64,{}"'.format(mime,data)
    body='<header><h1>'+esc(clean_display_name(state.title))+'</h1>'
    for label,value in (('Study',state.study_name),('Author',state.author),('Notes',state.notes)):
        if value: body+='<p><b>'+label+':</b> '+esc(value)+'</p>'
    body+='</header><div class="tools"><button type="button" data-sections="open">Expand all</button><button type="button" data-sections="close">Collapse all</button></div><nav aria-label="Report sections">'
    body+=' · '.join('<a href="#section-{}">{}</a>'.format(i,esc(clean_display_name(section.title))) for i,section in enumerate(sections))+'</nav>'
    for i,section in enumerate(sections):
        body+='<details id="section-{}"{}><summary>{}. {}</summary><div class="section-body">'.format(i,' open' if i==0 else '',i+1,esc(clean_display_name(section.title)))
        body+=section.body+''.join(table.html() for table in section.tables)+''.join(figure.image_html for figure in section.figures)
        body+='</div></details>'
    body=re.sub(r'src\s*=\s*([\'"])(.*?)\1',embedded,body,flags=re.I)
    def local_link(match):
        key=match.group(2).split(':',1)[-1].strip('/')
        words={'validation':'validation','interpolation':'interpolation','comparison':'map comparison','diagnostics':'diagnostic'}
        word=words.get(key,key)
        target=next((i for i,section in enumerate(sections) if word in section.title.lower() or word in section.key.lower()),None)
        return 'href="#section-{}"'.format(target) if target is not None else 'aria-disabled="true"'
    body=re.sub(r'href\s*=\s*([\'"])(bfi:[^\'"]+)\1',local_link,body,flags=re.I)
    css='''body{font:16px/1.5 Arial,sans-serif;color:#142b42;margin:0 auto;padding:24px;max-width:1080px;background:#fff}
    h1{color:#092447}nav{padding:12px;background:#edf6f8;border-radius:7px}a{color:#008eab}
    .tools{display:flex;gap:8px;margin:14px 0}button{background:#edf6f8;color:#092447;border:1px solid #cad8df;border-radius:6px;padding:8px 14px;cursor:pointer}
    details{margin:18px 0;border-bottom:1px solid #cad8df;scroll-margin-top:16px}summary{cursor:pointer;font-weight:bold;color:#008eab;padding:10px 0}
    table{border-collapse:collapse;width:100%;margin:12px 0}td,th{border:1px solid #cad8df;padding:7px;text-align:left}
    th{background:#e5f2f5}.section-body{overflow:auto;padding-bottom:14px}.figure-block{text-align:center}
    img{max-width:100%;height:auto}.figure-caption{color:#536a7d;font-size:.9em}
    @media print{nav,.tools{display:none}details{break-inside:avoid}}'''
    script='''document.querySelectorAll('[data-sections]').forEach(function(button){button.addEventListener('click',function(){document.querySelectorAll('details').forEach(function(section){section.open=button.dataset.sections==='open';});});});
    function reveal(id){var section=document.getElementById(id);if(section){section.open=true;section.scrollIntoView({block:'start'});}}
    document.querySelectorAll('a[href^="#section-"]').forEach(function(link){link.addEventListener('click',function(event){event.preventDefault();var id=link.getAttribute('href').slice(1);history.replaceState(null,'','#'+id);reveal(id);});});
    window.addEventListener('hashchange',function(){reveal(location.hash.slice(1));});
    if(location.hash){reveal(location.hash.slice(1));}
    var printStates=[];window.addEventListener('beforeprint',function(){printStates=[];document.querySelectorAll('details').forEach(function(section){printStates.push(section.open);section.open=true;});});
    window.addEventListener('afterprint',function(){document.querySelectorAll('details').forEach(function(section,i){section.open=printStates[i];});});'''
    output='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'"><title>'+esc(state.title)+'</title><style>'+css+'</style></head><body>'+body+'<script>'+script+'</script></body></html>'
    Path(path).write_text(output,encoding='utf-8')
    return str(path)


class TemporaryHtmlReport:
    """Own immutable browser previews until the corresponding plugin window dies."""
    def __init__(self):
        import tempfile
        self.directory=tempfile.TemporaryDirectory(prefix='bfi-report-')
        self.count=0

    def render(self,state):
        from pathlib import Path
        self.count+=1
        path=Path(self.directory.name)/('report_{}.html'.format(self.count))
        return export_report_html(state,str(path))

    def cleanup(self):
        self.directory.cleanup()
