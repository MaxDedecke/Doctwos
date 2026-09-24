# Doctus MCP im Entwicklungsworkflow

- Wenn du Aufrufketten, Symbolverwendungen, Abhängigkeiten oder die Auswirkungen einer Codeänderung beurteilst, ziehe die passenden lesenden Tools des MCP-Servers `doctus` heran, sofern das Repository in Doctus indiziert ist.
- Ermittle die Projekt-ID zuerst aus `.vscode/settings.json` (`doctus.projectId`). Fehlt sie, suche das Projekt mit `doctus/list_visible_projects`; rate keine ID.
- Nutze `doctus/search_code`, um ein Symbol oder einen Pfad zu finden, `doctus/get_code_entity` für den konkreten Treffer und `doctus/get_call_flow` oder `doctus/get_graph_neighbors` für Beziehungen. Nutze `doctus/search_knowledge` für Fragen zu indizierten Dokumenten.
- Rufe bei einer solchen Analyse mindestens ein fachlich passendes Doctus-Tool auf, bevor du eine Aussage über Beziehungen oder Auswirkungen als geprüft darstellst. Wähle weitere Tools nach der Frage, statt alle pauschal aufzurufen.
- Gleiche Doctus-Treffer mit dem aktuellen Quellcode oder Diff ab: Der Index kann älter als der Workspace sein. Bezeichne nicht indizierte Änderungen nicht als durch Doctus validiert.
- Wenn der Server, ein Tool oder der passende Index nicht verfügbar ist, nenne die konkrete Lücke im Ergebnis. Gib eine reine Quellcode-Analyse nicht als Doctus-Prüfung aus.
