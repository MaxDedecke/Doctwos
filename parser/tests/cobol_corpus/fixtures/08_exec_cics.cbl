       IDENTIFICATION DIVISION.
       PROGRAM-ID. EXECDEMO.
       PROCEDURE DIVISION.
       MAIN-PARA.
           EXEC CICS
               SEND TEXT FROM('HELLO. WORLD.')
               LENGTH(13)
           END-EXEC.
           STOP RUN.
