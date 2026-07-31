       IDENTIFICATION DIVISION.
       PROGRAM-ID. EXECSQL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-DEPT-ID          PIC X(4).
       01  WS-EMP-ID           PIC 9(6).
       01  WS-EMP-NAME         PIC X(30).
       PROCEDURE DIVISION.
       MAIN-PARA.
           EXEC SQL
               DECLARE EMP-CURSOR CURSOR FOR
               SELECT EMP-ID, EMP-NAME
                 FROM EMPLOYEE
                WHERE DEPT-ID = :WS-DEPT-ID
           END-EXEC.
           EXEC SQL
               OPEN EMP-CURSOR
           END-EXEC.
           EXEC SQL
               FETCH EMP-CURSOR
                 INTO :WS-EMP-ID, :WS-EMP-NAME
           END-EXEC.
           EXEC SQL
               CLOSE EMP-CURSOR
           END-EXEC.
           STOP RUN.
