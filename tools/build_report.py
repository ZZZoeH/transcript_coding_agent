"""Build the editable report draft. Run with bundled Python containing python-docx."""
from pathlib import Path
import re
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'deliverables'
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
sec.top_margin = sec.bottom_margin = sec.left_margin = sec.right_margin = Inches(1)
sec.header_distance = sec.footer_distance = Inches(0.45)
for name in ['Normal', 'Title', 'Subtitle', 'Heading 1', 'Heading 2', 'Heading 3']:
    style = doc.styles[name]
    style.font.name = 'Arial'; style.font.size = Pt(12); style.font.color.rgb = RGBColor(0,0,0)
    style.paragraph_format.line_spacing = 1
    style.paragraph_format.space_after = Pt(6)
for name in ['Heading 1','Heading 2','Heading 3']:
    doc.styles[name].font.bold = True
    doc.styles[name].paragraph_format.space_before = Pt(12)
    doc.styles[name].paragraph_format.keep_with_next = True

def p(text='', style=None): return doc.add_paragraph(text, style)

def centered(text, size=12, bold=False, before=0, after=12):
    para=p(); para.alignment=WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.space_before=Pt(before);para.paragraph_format.space_after=Pt(after)
    run=para.add_run(text); run.bold=bold;run.font.size=Pt(size)
    return para

centered('CSE 598/494',14,before=30)
centered('Forensics Computing',14)
centered('Project Report',16,bold=True,after=70)
para=centered('Codebook guided coding of scam call transcripts',20,bold=True,after=45)
para.style=doc.styles['Title']
centered('By')
centered('Tech Girls',14,bold=True)
for name in ['Mansi Ganga Nayak','Ju-Won Hyun','Shuyi Huang','Pin-Jun Liu']: centered(name,after=8)
centered('December 7, 2026',before=40)
centered('DRAFT   Live model results and human studies pending',bold=True,before=20)
doc.add_page_break()

lines=(OUT/'report_draft.md').read_text().splitlines()
i=0
while i<len(lines):
    line=lines[i]
    if i==0 or line.startswith('Report draft for CSE'):i+=1;continue
    if not line.strip():i+=1;continue
    if line.startswith('|'):
        rows=[]
        while i<len(lines) and lines[i].startswith('|'):
            if not re.fullmatch(r'[|\- :]+',lines[i]): rows.append([x.strip() for x in lines[i].strip('|').split('|')])
            i+=1
        table=doc.add_table(rows=0,cols=len(rows[0]));table.autofit=False
        widths = ([1.8,1.0,0.7,3.0] if len(rows[0])==4 and 'Metric' in rows[0] else
                  [1.8,1.57,1.57,1.56] if len(rows[0])==4 else [1.35,2.6,2.55])
        for j,w in enumerate(widths): table.columns[j].width=Inches(w)
        for ri,values in enumerate(rows):
            cells=table.add_row().cells
            for ci,text in enumerate(values):
                cells[ci].width=Inches(widths[ci]);cells[ci].text=text
                tcpr=cells[ci]._tc.get_or_add_tcPr()
                borders=OxmlElement('w:tcBorders')
                for edge in ['top','left','bottom','right']:
                    tag=OxmlElement('w:'+edge);tag.set(qn('w:val'),'single');tag.set(qn('w:sz'),'4');tag.set(qn('w:color'),'D9D9D9');borders.append(tag)
                tcpr.append(borders)
                margins=OxmlElement('w:tcMar')
                for edge in ['top','bottom','left','right']:
                    tag=OxmlElement('w:'+edge);tag.set(qn('w:w'),'85');tag.set(qn('w:type'),'dxa');margins.append(tag)
                tcpr.append(margins)
                if ri==0:
                    shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'E8E8E8');tcpr.append(shade)
                for para in cells[ci].paragraphs:
                    para.paragraph_format.space_after=Pt(2)
                    for run in para.runs: run.font.size=Pt(12);run.bold=(ri==0)
            trpr=table.rows[-1]._tr.get_or_add_trPr()
            if ri==0: trpr.append(OxmlElement('w:tblHeader'))
            trpr.append(OxmlElement('w:cantSplit'))
        p();continue
    if line.startswith('### '):p(line[4:], 'Heading 2')
    elif line.startswith('## '):p(line[3:], 'Heading 1')
    else:p(line)
    i+=1

doc.add_page_break()
p('Academic integrity','Heading 1')
p('Mandatory attachment   All project members should read and confirm their understanding with their full name and signature.')
# Text retained from the supplied course requirement; signatures are intentionally blank.
for text in [
 'The university and the school expect the highest standards of academic integrity of all students. Failure to meet these standards may result in suspension or expulsion from the university or other sanctions as specified in the University Student Academic Integrity Policy. Please take some time to read the policy at https://provost.asu.edu/academic-integrity',
 'In addition, ASU adheres to a university-wide Student Code of Conduct. The philosophy behind this policy states: The aim of education is the intellectual, personal, social, and ethical development of the individual. The educational process is ideally conducted in an environment that encourages reasoned discourse, intellectual honesty, openness to constructive change and respect for the rights of all individuals. Self-discipline and a respect for the rights of others in the university community are necessary for the fulfillment of such goals. The Student Code of Conduct is designed to promote this environment at each of the state universities.']:
 p(text)
for _ in range(4):
    para=p('STUDENT ID (4digit): __________   NAME: ____________________')
    para.paragraph_format.space_before=Pt(12)
    p('DATE: __________________   Signature: _______________________')
footer=sec.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
run=footer.add_run('Draft   ');run.font.size=Pt(10)
fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');footer._p.append(fld)
doc.core_properties.title='Codebook guided coding of scam call transcripts'
doc.core_properties.author='Tech Girls'
doc.core_properties.subject='CSE 598/494 report draft with pending experiments'
# Remove inherited paragraph borders, including Word's default Title rule.
for element in [doc.styles.element, doc.element]:
    for border in list(element.iter(qn('w:pBdr'))): border.getparent().remove(border)
doc.save(OUT/'Project_Report_Draft.docx')
print(OUT/'Project_Report_Draft.docx')
