import json
from cobol.parse import parse_program
from cobol.profile import BuildProfile
from cobol.model import CobolProgram
from cobol.embedded import EmbeddedBlock
from cobol import sql, exec as exec_parser

def inspect(name,text):
 r=parse_program(text,name+'.cbl',profile=BuildProfile(source_format='free'))
 print(json.dumps({'case':name,'entities':[{'name':e.name,'type':e.type,'meta':e.meta} for e in r.entities if e.type in ['data_item','file_fd']],'edges':[{'type':e.type,'source':e.src_name,'target':e.dst_name,'meta':e.meta} for e in r.edges],'errors':r.errors,'diagnostics':[(d.code,d.line,d.message[:100]) for d in r.diagnostics if d.severity!='info']},ensure_ascii=False),flush=True)
inspect('data', '''IDENTIFICATION DIVISION.
PROGRAM-ID. AUDITDATA.
DATA DIVISION.
WORKING-STORAGE SECTION.
01 STATE-CODE PIC 9.
 88 ACCEPTED VALUES 1 THRU 3, 7.
01 PACKED-AMOUNT PIC S9(7)V99 COMP-3.
01 GROUP-AREA.
 05 FIRST-PART PIC X.
 05 LAST-PART PIC X.
66 BOTH-PARTS RENAMES FIRST-PART THRU LAST-PART.
LOCAL-STORAGE SECTION.
01 LOCAL-AMOUNT PIC 9(4).
PROCEDURE DIVISION.
MAIN-PARA.
 MOVE 1 TO LOCAL-AMOUNT
 STOP RUN.
''')
inspect('control', '''IDENTIFICATION DIVISION.
PROGRAM-ID. AUDITCONTROL.
DATA DIVISION.
WORKING-STORAGE SECTION.
01 TIMES-N PIC 9 VALUE 3.
PROCEDURE DIVISION.
MAIN-PARA.
 PERFORM TIMES-N TIMES
 DISPLAY 'X'
 END-PERFORM
 IF TIMES-N = 1
 GO TO DONE-PARA
 ELSE
 DISPLAY 'Y'
 END-IF.
DONE-PARA.
 STOP RUN.
''')
inspect('io', '''IDENTIFICATION DIVISION.
PROGRAM-ID. AUDITIO.
ENVIRONMENT DIVISION.
INPUT-OUTPUT SECTION.
FILE-CONTROL.
 SELECT IN-FILE ASSIGN TO 'INPUT.DAT'.
 SELECT OUT-FILE ASSIGN TO 'OUTPUT.DAT'.
DATA DIVISION.
FILE SECTION.
FD IN-FILE.
01 IN-REC PIC X(10).
FD OUT-FILE.
01 OUT-REC PIC X(10).
WORKING-STORAGE SECTION.
01 BUFFER-DATA PIC X(10).
PROCEDURE DIVISION.
MAIN-PARA.
 WRITE OUT-REC
 WRITE OUT-REC FROM BUFFER-DATA
 CLOSE IN-FILE OUT-FILE
 STOP RUN.
''')
p=CobolProgram(name='SQLCHECK',start_line=1,end_line=10)
for query in ['SELECT AMOUNT INTO :RESULT-VALUE FROM BANK.ACCOUNTS WHERE ID = :LOOKUP-ID', "SELECT NAME FROM ACCOUNTS WHERE NOTE = 'JOIN FAKE-TABLE'", 'INSERT INTO TARGET-TABLE SELECT VALUE FROM SOURCE-TABLE']:
 blocks,edges,errors=sql.scan(p,[EmbeddedBlock('SQL',1,1,'EXEC SQL '+query+' END-EXEC')])
 print(json.dumps({'sql':query,'tables':blocks[0].tables,'edges':[(e.type,e.dst_name) for e in edges]}),flush=True)
for query in ["EXEC CICS READ FILE('ACCT') INTO(ACCOUNT-REC) RESP(RESP-CODE) END-EXEC",'EXEC DLI ISRT SEGMENT(PAUTDTL1) FROM(PENDING-AUTH-DETAILS) END-EXEC']:
 dialect='CICS' if 'CICS' in query else 'DLI'
 b,e,_=exec_parser.scan(p,[EmbeddedBlock(dialect,1,1,query)])
 print(json.dumps({'exec':query,'resources':[(x.kind,x.name) for x in b[0].resources],'edges':[(x.type,x.dst_name) for x in e]}),flush=True)
