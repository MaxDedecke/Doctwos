identification division.
program-id. DIALECTTEST.
data division.
working-storage section.
01 FLAG PIC X.
procedure division.
MAIN-PARA.
>>IF 1 = 1
    call "ACTIVE".
>>ELSE
    call "INACTIVE".
>>END-IF
    goback.
