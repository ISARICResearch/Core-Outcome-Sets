from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

# ---- palette ----
AUTO = "D9D9D9"   # grey  - deterministic, no tokens
AI   = "DDEBF7"   # blue  - LLM judgement
HUM  = "FCE4D6"   # amber - human review/override
HEAD = "1F4E79"   # dark blue title
WHITE="FFFFFF"
thin = Side(style="thin", color="BFBFBF")
border = Border(left=thin,right=thin,top=thin,bottom=thin)
F = "Arial"

wb = Workbook()

# ===================== REF SHEETS =====================
dodd = ["1. Mortality/survival","2. Blood and lymphatic system outcomes","3. Cardiac outcomes",
"4. Congenital, familial and genetic outcomes","5. Endocrine outcomes","6. Ear and labyrinth outcomes",
"7. Eye outcomes","8. Gastrointestinal outcomes","9. General outcomes","10. Hepatobiliary outcomes",
"11. Immune system outcomes","12. Infection and infestation outcomes","13. Injury and poisoning outcomes",
"14. Metabolism and nutrition outcomes","15. Musculoskeletal and connective tissue outcomes",
"16. Outcomes relating to neoplasms: benign, malignant and unspecified (including cysts and polyps)",
"17. Nervous system outcomes","18. Pregnancy, puerperium and perinatal outcomes",
"19. Renal and urinary outcomes","20. Reproductive system and breast outcomes","21. Psychiatric outcomes",
"22. Respiratory, thoracic and mediastinal outcomes","23. Skin and subcutaneous tissue outcomes",
"24. Vascular outcomes","25. Physical functioning","26. Social functioning","27. Role functioning",
"28. Emotional functioning/wellbeing","29. Cognitive functioning","30. Global quality of life",
"31. Perceived health status","32. Delivery of care","33. Personal circumstances","34. Economic",
"35. Hospital","36. Need for further intervention","37. Societal/carer burden","38. Adverse events/effects"]


# small controlled lists (each becomes a column in Ref_Lists)
lists = {
 "Type of outcome":["Primary","Secondary","Other","Exploratory","Unclear"],
 "OMI type":["PROM (patient-reported)","ClinROM (clinician-reported)","ObsROM (observer-reported)",
             "PerfO (performance)","OOM (objective measure)","Composite OMI","Not specified"],
 "Metric":["Proportion / incidence","Time-to-event","Change from baseline","Mean / geometric-mean value",
           "Absolute value / level","AUC","Categorical","Binary presence/absence","Score / score change","Not stated"],
 "Source registry":["ClinicalTrials.gov","ICTRP: EUCTR","ICTRP: ISRCTN","ICTRP: CTRI","ICTRP: ChiCTR",
                    "ICTRP: JPRN","ICTRP: ANZCTR","ICTRP: other"],
 "Record type":["Registry record (protocol)","Journal article","Results posting"],
 "Funder type":["Industry","Government","Academic / Hospital","Charity / Non-profit","Other","Unclear"],
 "Income group":["HIC","UMIC","LMIC","LIC","Mixed / multi-country","Unclear"],
 "Phase":["Phase 1","Phase 1/2","Phase 2","Phase 2/3","Phase 3","Phase 4","N/A","Not stated"],
 "Study type":["Interventional","Observational","Qualitative","Other"],
 "Sex":["All","Male","Female"],
 "Confidence":["High","Medium","Low"],
 "Yes/No":["Y","N"],
 "Extracted by":["Auto","AI","Human"],
 "Reviewer decision":["Accept","Edit","Reject"],
 "Screen decision":["Include","Exclude","Unsure"],
 "Duplicate flag":["Unique","Duplicate – removed"],
 "Match basis":["Exact registry ID","ICTRP bridge flag","Shared secondary ID","Fuzzy (title+sponsor+date)","Manual"],
 "Human screen":["Include","Exclude"],
}

def style_header(ws, row, fills):
    for c,(txt,fill) in enumerate(fills, start=1):
        cell = ws.cell(row=row, column=c, value=txt)
        cell.font = Font(name=F, bold=True, color="000000", size=10)
        cell.fill = PatternFill("solid", fgColor=fill)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border

# ---- Ref_Dodd ----
wd = wb.active; wd.title = "Ref_Dodd"
wd["A1"]="Outcome domains – Dodd et al. (2018) taxonomy"; wd["A1"].font=Font(name=F,bold=True)
for i,v in enumerate(dodd, start=2): wd.cell(row=i,column=1,value=v).font=Font(name=F,size=10)
wd.column_dimensions["A"].width=70


# ---- Ref_Lists ----
wl = wb.create_sheet("Ref_Lists")
for ci,(name,vals) in enumerate(lists.items(), start=1):
    wl.cell(row=1,column=ci,value=name).font=Font(name=F,bold=True,size=10)
    for ri,v in enumerate(vals, start=2):
        wl.cell(row=ri,column=ci,value=v).font=Font(name=F,size=10)
    wl.column_dimensions[get_column_letter(ci)].width=max(14,len(name)+2)

def list_ref(name):
    ci = list(lists.keys()).index(name)+1
    L = get_column_letter(ci)
    n = len(lists[name])+1
    return f"=Ref_Lists!${L}$2:${L}${n}"

def add_dv(ws, formula, col, first=2, last=1000):
    dv = DataValidation(type="list", formula1=formula, allow_blank=True)
    dv.error="Pick a value from the list"; dv.errorTitle="Controlled vocabulary"
    ws.add_data_validation(dv)
    L=get_column_letter(col)
    dv.add(f"{L}{first}:{L}{last}")

# ===================== SHEET 1: SCREENING =====================
s1 = wb.create_sheet("1. Screening")
# title + PRISMA block
s1["A1"]="PART 1 — De-duplication & AI screening (PRISMA identification stage)"
s1["A1"].font=Font(name=F,bold=True,size=12,color=HEAD)
prisma=[("N identified — ClinicalTrials.gov","=COUNTIF(B14:B100000,\"ClinicalTrials.gov\")"),
        ("N identified — ICTRP (all registries)","=COUNTIF(B14:B100000,\"ICTRP*\")"),
        ("N total records identified","=COUNTA(A14:A100000)"),
        ("N duplicates removed","=COUNTIF(L14:L100000,\"Duplicate*\")"),
        ("N screened (unique)","=COUNTIF(L14:L100000,\"Unique\")"),
        ("N excluded by AI","=COUNTIFS(L14:L100000,\"Unique\",O14:O100000,\"Exclude\")"),
        ("N included after screening","=COUNTIFS(L14:L100000,\"Unique\",O14:O100000,\"Include\")")]
for i,(lab,frm) in enumerate(prisma, start=3):
    s1.cell(row=i,column=1,value=lab).font=Font(name=F,size=10,bold=True)
    c=s1.cell(row=i,column=2,value=frm); c.font=Font(name=F,size=10)
    c.fill=PatternFill("solid",fgColor="FFF2CC")
s1["D3"]="◀ auto-counts from the table below"; s1["D3"].font=Font(name=F,italic=True,size=9,color="808080")

s1_cols=[("record_id",AUTO),("Source registry(ies)",AUTO),("Registry ID(s)",AUTO),("Secondary IDs",AUTO),
("Title",AUTO),("Condition",AUTO),("Intervention",AUTO),("Study type",AUTO),("Phase",AUTO),
("Recruitment status",AUTO),("Registration date",AUTO),
("Duplicate?",AUTO),("Duplicate of (record_id)",AUTO),("Match basis",AUTO),
("AI decision",AI),("Exclusion criterion ID",AI),("Reason (short)",AI),("AI confidence",AI),("Needs review",AI),
("Human decision",HUM),("Reviewer",HUM),("Comments",HUM)]
HROW1=13
style_header(s1,HROW1,s1_cols)
widths1=[10,18,16,16,40,22,28,14,12,16,14,16,16,20,12,16,32,12,12,14,12,30]
for i,w in enumerate(widths1, start=1): s1.column_dimensions[get_column_letter(i)].width=w
s1.freeze_panes="A14"
# dropdowns
add_dv(s1, "=Ref_Lists!$P$2:$P$3", 12, first=14)            # Duplicate flag
add_dv(s1, list_ref("Match basis"), 14, first=14)
add_dv(s1, list_ref("Screen decision"), 15, first=14)
add_dv(s1, list_ref("Confidence"), 18, first=14)
add_dv(s1, list_ref("Yes/No"), 19, first=14)
add_dv(s1, list_ref("Human screen"), 20, first=14)

# ===================== SHEET 2: EXTRACTION =====================
s2 = wb.create_sheet("2. Extraction")
s2["A1"]="PART 2 — Outcome & OMI extraction  (one row per outcome)"
s2["A1"].font=Font(name=F,bold=True,size=12,color=HEAD)
s2["A2"]=("Grey = auto-filled from registry (no AI) · Blue = AI judgement · Amber = human review.  "
          "Rule: OUTCOME = what is measured · OMI = how it is measured · METRIC = analytic form.")
s2["A2"].font=Font(name=F,italic=True,size=9,color="595959")

s2_cols=[("record_id",AUTO),("Source registry",AUTO),("Registry ID",AUTO),("Secondary IDs",AUTO),
("Record type",AUTO),("Title",AUTO),("Link",AUTO),
("Sponsor / Funder",AUTO),("Funder type",AI),("Country",AUTO),("Income group",AI),("Year",AUTO),
("Study design",AUTO),("Phase",AUTO),("Study type",AUTO),("Condition",AUTO),("Intervention",AUTO),
("Control type",AI),("Population characteristic",AI),("Age range",AUTO),("Sex",AUTO),("Sample size",AUTO),
("★ Verbatim outcome (as registered)",AUTO),("Outcome (WHAT is measured)",AI),("Description / definition",AUTO),
("Type of outcome",AUTO),("Outcome domain (Dodd)",AI),
("OMI – instrument (HOW measured)",AI),("OMI type",AI),("Metric",AI),("Time frame / timepoint",AUTO),
("Additional data",AI),
("Extracted by",HUM),("AI confidence",AI),("Needs review",AI),("Reviewer 1",HUM),("Reviewer 2",HUM),
("Reviewer decision",HUM),("Comments",HUM)]
HROW2=3
style_header(s2,HROW2,s2_cols)
widths2=[10,16,14,16,22,40,26, 24,16,16,14,10, 22,12,16,24,28, 16,24,12,10,12,
         46,28,40, 16,30, 34,20,22,22, 26, 12,12,12,12,12,16,30]
for i,w in enumerate(widths2, start=1): s2.column_dimensions[get_column_letter(i)].width=w
s2.freeze_panes="A4"
# dropdowns mapped by header NAME (robust to column changes)
name_dv = {"Source registry":list_ref("Source registry"),"Record type":list_ref("Record type"),
"Funder type":list_ref("Funder type"),"Income group":list_ref("Income group"),"Phase":list_ref("Phase"),
"Study type":list_ref("Study type"),"Sex":list_ref("Sex"),"Type of outcome":list_ref("Type of outcome"),
"Outcome domain (Dodd)":"=Ref_Dodd!$A$2:$A$39","OMI type":list_ref("OMI type"),"Metric":list_ref("Metric"),
"Extracted by":list_ref("Extracted by"),"AI confidence":list_ref("Confidence"),
"Needs review":list_ref("Yes/No"),"Reviewer decision":list_ref("Reviewer decision")}
hdr_idx = {c[0]:i+1 for i,c in enumerate(s2_cols)}
for name,frm in name_dv.items():
    if name in hdr_idx: add_dv(s2, frm, hdr_idx[name], first=4)

# ===================== CODEBOOK =====================
cb = wb.create_sheet("READ ME – Codebook"); 
wb.move_sheet("READ ME – Codebook", -(len(wb.sheetnames)-1))  # move to front
cb["A1"]="COS extraction template — how it works"; cb["A1"].font=Font(name=F,bold=True,size=14,color=HEAD)
rows=[
 ("",""),
 ("COLOUR CODE (who fills each column)",""),
 ("  Grey","Auto-filled deterministically from the CTG / ICTRP download — NO AI, NO tokens."),
 ("  Blue","AI judgement (categorisation / decomposition). Always paired with a confidence + review flag."),
 ("  Amber","Human reviewer: check, edit, accept/reject."),
 ("",""),
 ("THE CORE RULE (Outcome vs OMI vs Metric)",""),
 ("  Outcome","WHAT is being measured — the concept.  e.g. 'fever resolution', 'immunogenicity', 'mortality'."),
 ("  OMI","HOW it is measured — the instrument/method.  e.g. 'axillary thermometry', 'PRNT50 assay', 'BDI scale'."),
 ("  Metric","The analytic form of the measure.  e.g. 'time-to-event', 'proportion', 'change from baseline', 'GM titre'."),
 ("  Time frame","WHEN it is measured — the timepoint(s)."),
 ("",""),
 ("WHY the '★ Verbatim outcome' column matters",
   "Registries cram the what + how + metric + timepoint into one string. The verbatim column keeps the original "
   "next to the AI decomposition so a reviewer can check the split at a glance without reopening the registry."),
 ("",""),
 ("WORKED EXAMPLES (from your own data)",""),
 ("  Registry text","'Percentage of subjects achieving seroconversion (≥1:10 in PRNT50 titre) at day 29'"),
 ("    → Outcome","immunogenicity / seroconversion"),
 ("    → OMI","PRNT50 neutralisation assay   |  OMI type: OOM (objective)"),
 ("    → Metric","Proportion / incidence    → Time frame: day 29"),
 ("  Registry text","'resolution of fever — time to temperature normalisation for ≥12 h'"),
 ("    → Outcome","fever resolution   |  Dodd: 9. General outcomes"),
 ("    → OMI","axillary thermometry  |  OMI type: ClinROM   |  Metric: Time-to-event"),
 ("",""),
 ("AUTOMATION BOUNDARY (token policy)",""),
 ("  Deterministic (no AI)","IDs, title, sponsor, country, dates, phase, age, sex, enrolment, condition, "
   "intervention, verbatim outcome text + its timepoint. Pull CTG from the v2 JSON API and these arrive pre-split."),
 ("  AI only where needed","Outcome/OMI/Metric decomposition, domain classification (closed lists), funder type, "
   "income group, control type, population. Everything AI touches gets a confidence + 'needs review' flag."),
 ("",""),
 ("DEDUPLICATION note","ICTRP already flags cross-registered records (columns 'Bridging flag', 'Bridged type', "
   "'other records', 'Secondary ID'). Use those first for exact merges; fall back to fuzzy title+sponsor+date only "
   "for the residue. Record the match basis so every removed duplicate is auditable."),
 ("",""),
 ("Reference tabs","Ref_Dodd = 38 Dodd domains (single classification layer) · Ref_Lists = all dropdown vocab."),
]
for i,(a,b) in enumerate(rows, start=2):
    ca=cb.cell(row=i,column=1,value=a); ca.font=Font(name=F,bold=(b=="" and a!=""),size=10,color=HEAD if (b=="" and a!="") else "000000")
    ca.alignment=Alignment(vertical="top")
    cbx=cb.cell(row=i,column=2,value=b); cbx.font=Font(name=F,size=10); cbx.alignment=Alignment(wrap_text=True,vertical="top")
cb.column_dimensions["A"].width=30; cb.column_dimensions["B"].width=95
# legend swatches
cb["A3"].fill=PatternFill("solid",fgColor=AUTO)
cb["A4"].fill=PatternFill("solid",fgColor=AI)
cb["A5"].fill=PatternFill("solid",fgColor=HUM)

# order sheets: codebook, screening, extraction, refs
order=["READ ME – Codebook","1. Screening","2. Extraction","Ref_Dodd","Ref_Lists"]
wb._sheets.sort(key=lambda s: order.index(s.title))
wb.active=0

out="/home/claude/work/COS_extraction_template_v1.xlsx"
wb.save(out)
print("saved", out)
print("sheets:", wb.sheetnames)
