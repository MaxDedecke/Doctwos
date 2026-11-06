       IDENTIFICATION DIVISION.
       PROGRAM-ID. NESTOUTER.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-IDX              PIC 9(4).
       01 CYCLE               PIC 9(4).
       PROCEDURE DIVISION.
       MAIN-SECTION SECTION.
       MAIN-PARA.
           PERFORM VARYING WS-IDX FROM 1 BY 1 UNTIL WS-IDX > 10
               IF WS-IDX = 3
                   EXIT PERFORM CYCLE
               END-IF
               IF WS-IDX = 7
                   EXIT PERFORM
               END-IF
               ADD 1 TO CYCLE
           END-PERFORM
           PERFORM CHECK-PARA
           CALL 'NESTINNER'
           GOBACK.
       CHECK-PARA.
           IF CYCLE > 5
               EXIT PARAGRAPH
           END-IF
           DISPLAY 'CHECKED'.
       LAST-SECTION SECTION.
       LAST-PARA.
           IF WS-IDX = 0
               EXIT SECTION
           END-IF
           DISPLAY 'DONE'.
           IDENTIFICATION DIVISION.
           PROGRAM-ID. NESTINNER.
           DATA DIVISION.
           WORKING-STORAGE SECTION.
           01 WS-IDX          PIC 9(4).
           PROCEDURE DIVISION.
           INNER-PARA.
               PERFORM UNTIL WS-IDX > 2
                   EXIT PERFORM
               END-PERFORM
               EXIT PROGRAM.
           END PROGRAM NESTINNER.
       END PROGRAM NESTOUTER.
