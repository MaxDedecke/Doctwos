       IDENTIFICATION DIVISION.
       PROGRAM-ID. GNUEXT IS RECURSIVE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       78 TABLE-CAPACITY       VALUE 10.
       01 WS-COUNT             BINARY-LONG UNSIGNED VALUE 0.
       01 WS-SMALL             BINARY-CHAR.
       01 WS-RATIO             FLOAT-LONG.
       01 WS-HANDLE            PIC X(4) USAGE COMP-X.
       01 WS-CALLBACK          PROGRAM-POINTER.
       01 WS-MASK   BINARY-SHORT SIGNED VALUE LENGTH OF WS-HANDLE.
       01 WS-TABLE.
          02 WS-ENTRY          OCCURS TABLE-CAPACITY TIMES BINARY-LONG.
       01 WS-DYN               BASED.
          02 WS-DYN-BYTE PIC X OCCURS UNBOUNDED
                         DEPENDING ON WS-COUNT.
       01 WS-PTR               USAGE POINTER.
       01 WS-TEXT              PIC X(40).
       LINKAGE SECTION.
       01 LK-NAME              PIC X ANY LENGTH.
       01 LK-OPTIONAL          PIC X(8).
       PROCEDURE DIVISION USING LK-NAME LK-OPTIONAL.
       MAIN-PARA.
           IF LK-OPTIONAL IS NOT OMITTED
               DISPLAY LK-OPTIONAL
           END-IF
           ALLOCATE WS-COUNT CHARACTERS RETURNING WS-PTR
           ALLOCATE WS-DYN INITIALIZED
           COMPUTE WS-MASK = WS-COUNT B-AND H'FF'
           COMPUTE WS-MASK = WS-MASK B-OR (WS-COUNT B-SHIFT-L 4)
           DIVIDE WS-COUNT BY 3 GIVING WS-COUNT
               ROUNDED MODE IS TOWARD-LESSER
           STRING "Name: " FUNCTION TRIM(LK-NAME, LEADING)
               INTO WS-TEXT
           MOVE X"0a0d" TO WS-HANDLE
           EVALUATE WS-COUNT
               WHEN < 5
                   PERFORM SMALL-PARA
               WHEN = 5 OR = 6
                   CONTINUE
               WHEN OTHER
                   SORT WS-ENTRY
           END-EVALUATE
           PERFORM UNTIL EXIT
               ADD 1 TO WS-COUNT
               IF WS-COUNT > 9
                   EXIT PERFORM
               END-IF
           END-PERFORM
           PERFORM FOREVER
               CALL 'WORKER' USING OMITTED WS-COUNT
               EXIT PERFORM
           END-PERFORM
           FREE WS-PTR
           GOBACK.
       SMALL-PARA.
           SET WS-CALLBACK TO ENTRY "SMALL-CALLBACK"
           DISPLAY 'SMALL'.
       END PROGRAM GNUEXT.
