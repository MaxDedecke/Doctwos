       IDENTIFICATION DIVISION.
       PROGRAM-ID. DATAQUAL.
       DATA DIVISION.
       FILE SECTION.
       FD  EMPLOYEE-FILE.
       01  EMPLOYEE-RECORD.
           05  EMP-ID          PIC 9(6).
           05  EMP-NAME        PIC X(30).
       WORKING-STORAGE SECTION.
       01  GROUP-A.
           05  WS-CODE         PIC X(2).
       01  GROUP-B.
           05  WS-CODE         PIC X(4).
       01  WS-COUNT            PIC 9(3) VALUE 0.
       01  WS-TABLE.
           05  WS-ENTRY        PIC X(10)
                               OCCURS 1 TO 50 TIMES
                               DEPENDING ON WS-COUNT.
       01  WS-ALT REDEFINES WS-TABLE PIC X(500).
       01  WS-EOF-FLAG         PIC X VALUE 'N'.
           88  WS-EOF                     VALUE 'Y'.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE 'AB' TO WS-CODE OF GROUP-A.
           MOVE WS-CODE OF GROUP-B TO WS-CODE OF GROUP-A.
           IF WS-EOF
               DISPLAY 'DONE'
           END-IF.
           STOP RUN.
