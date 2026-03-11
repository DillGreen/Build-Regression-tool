# Examples

This page shows common ways to run Build Regression Tool.

## Compare Two Build Logs

python builddiff_advanced.py baseline_log.txt candidate_log.txt
<img width="1307" height="1349" alt="image" src="https://github.com/user-attachments/assets/95e5f877-9a0e-4409-acef-fa4122a990c6" />

JSON: python builddiff_advanced.py baseline_log.txt candidate_log.txt --json
<img width="1536" height="2024" alt="image" src="https://github.com/user-attachments/assets/56fa1ef0-ffd0-4fae-8aff-efa3427e4fcb" />

Markdown: python builddiff_advanced.py baseline_log.txt candidate_log.txt --markdown
<img width="990" height="422" alt="image" src="https://github.com/user-attachments/assets/fa3538a5-a4ac-40ef-b5bb-2c161cd0632d" />

HTML: python builddiff_advanced.py baseline_log.txt candidate_log.txt --html --html-out report.html
<img width="898" height="197" alt="image" src="https://github.com/user-attachments/assets/349077f0-0fdd-4f55-9de3-f88d49484d29" />
(Ignore Debugg logs, check file location of the code and those 2 files and you should see a new HTML file to open)
<img width="1947" height="1907" alt="image" src="https://github.com/user-attachments/assets/0361a7c4-2815-42d2-bf1a-b32ffd97ef08" />

Synthetic Test Mode: python builddiff_advanced.py --synthetic     (The numbers are hard coded and the results of the report will automatically append to history
<img width="995" height="1654" alt="image" src="https://github.com/user-attachments/assets/ae75b466-09f6-4e6b-85b1-a9d1ab7dbad3" />
These are other flags that can be used 
  python builddiff_advanced.py --synthetic --json
  python builddiff_advanced.py --synthetic --markdown
  python builddiff_advanced.py --synthetic --html --html-out synthetic_report.html

To track history: across comparisons add the flag " --track " to the end of any of the listed flags above and it will track 

History Analysis: python builddiff_advanced.py --history
<img width="870" height="258" alt="image" src="https://github.com/user-attachments/assets/732df924-f756-491b-a194-24afa2e69f0e" />

CI Mode: python builddiff_advanced.py baseline_log.txt candidate_log.txt --ci
  You can also customize threhold numbers, python builddiff_advanced.py baseline_log.txt candidate_log.txt --ci --fail-percent 40 --fail-seconds 30
<img width="1328" height="1400" alt="image" src="https://github.com/user-attachments/assets/cc9a65ed-6853-47fd-82e8-c1277cf9f4be" />

Build Output Size Calculation ( Still in development may not path correctly)
This tells the tool to calculate candidate build size directly from the output file or folder.
: python builddiff_advanced.py baseline_log.txt candidate_log.txt --build-output "C:\Path\To\Build"

Platform Override: python builddiff_advanced.py baseline_log.txt candidate_log.txt --platform StandaloneWindows64
<img width="1287" height="1363" alt="image" src="https://github.com/user-attachments/assets/ec1d1819-4d6c-4f24-86a0-fe87567f8989" />







