# Codena MCP im Entwicklungsworkflow

- Wenn du Aufrufketten, Symbolverwendungen, Abhängigkeiten oder die Auswirkungen einer Codeänderung beurteilst, ziehe die passenden lesenden Tools des MCP-Servers `codena` heran, sofern das Repository in Codena indiziert ist.
- Ermittle die Projekt-ID zuerst aus `.vscode/settings.json` (`codena.projectId`). Fehlt sie, suche das Projekt mit `codena/list_visible_projects`; rate keine ID.
- Nutze `codena/search_code`, um ein Symbol oder einen Pfad zu finden, `codena/get_code_entity` für den konkreten Treffer und `codena/get_call_flow` oder `codena/get_graph_neighbors` für Beziehungen. Nutze `codena/search_knowledge` für Fragen zu indizierten Dokumenten.
- Rufe bei einer solchen Analyse mindestens ein fachlich passendes Codena-Tool auf, bevor du eine Aussage über Beziehungen oder Auswirkungen als geprüft darstellst. Wähle weitere Tools nach der Frage, statt alle pauschal aufzurufen.
- Gleiche Codena-Treffer mit dem aktuellen Quellcode oder Diff ab: Der Index kann älter als der Workspace sein. Bezeichne nicht indizierte Änderungen nicht als durch Codena validiert.
- Wenn der Server, ein Tool oder der passende Index nicht verfügbar ist, nenne die konkrete Lücke im Ergebnis. Gib eine reine Quellcode-Analyse nicht als Codena-Prüfung aus.
