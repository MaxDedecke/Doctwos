"""Source-backed branch and loop guards for Java invocation edges."""

from ._antlr.JavaParser import JavaParser


def _list(value):
    return value if isinstance(value, list) else [value] if value is not None else []


def _switch_label(rule, text):
    if rule.DEFAULT() is not None and rule.CASE() is None:
        return "default"
    if rule.expressionList() is not None:
        value = text(rule.expressionList())
    elif rule.casePattern():
        value = ", ".join(text(pattern) for pattern in rule.casePattern())
    else:
        value = "null" + (", default" if rule.DEFAULT() is not None else "")
    if rule.guard() is not None:
        value += " " + text(rule.guard())
    return "case " + value


def control_path(context, text, stop_rules):
    """Return outer-to-inner guards; evaluating a selector is not a branch."""
    path = []
    child, current = context, context.parentCtx
    while current is not None:
        rule = JavaParser.ruleNames[current.getRuleIndex()]
        if rule in stop_rules:
            break
        if isinstance(current, JavaParser.TernaryExpressionContext):
            expressions = current.expression()
            if child in expressions[1:]:
                path.append(
                    {
                        "type": "IF",
                        "branch": "THEN" if child is expressions[1] else "ELSE",
                        "condition": text(expressions[0]),
                    }
                )
        elif isinstance(current, JavaParser.BinaryOperatorExpressionContext):
            expressions = current.expression()
            operator = current.bop.text if current.bop is not None else None
            if operator in {"&&", "||"} and child is expressions[1]:
                path.append(
                    {
                        "type": "IF",
                        "branch": "THEN" if operator == "&&" else "ELSE",
                        "condition": text(expressions[0]),
                    }
                )
        elif rule == "switchLabeledRule" and child is current.switchRuleOutcome():
            switch = current.parentCtx
            path.append(
                {
                    "type": "SWITCH",
                    "branch": "CASE",
                    "subject": text(switch.expression()),
                    "when": _switch_label(current, text),
                }
            )
        elif rule == "statement" and current.start is not None:
            keyword = current.start.text.casefold()
            statements = _list(current.statement())
            expressions = _list(current.expression())
            body = child in statements
            if keyword == "if" and body and expressions:
                path.append(
                    {
                        "type": "IF",
                        "branch": "ELSE"
                        if len(statements) > 1 and child is statements[1]
                        else "THEN",
                        "condition": text(expressions[0]),
                    }
                )
            elif keyword in {"while", "do"} and body and expressions:
                path.append(
                    {
                        "type": "LOOP",
                        "kind": "WHILE" if keyword == "while" else "DO_WHILE",
                        "text": text(expressions[0]),
                    }
                )
            elif keyword == "for" and body:
                control = current.forControl()
                each = control is not None and control.enhancedForControl() is not None
                path.append(
                    {"type": "LOOP", "kind": "FOR_EACH" if each else "FOR", "text": text(control)}
                )
            elif (
                keyword == "switch"
                and expressions
                and rule_name(child) == "switchBlockStatementGroup"
            ):
                path.append(
                    {
                        "type": "SWITCH",
                        "branch": "CASE",
                        "subject": text(expressions[0]),
                        "when": ", ".join(text(label) for label in _list(child.switchLabel())),
                    }
                )
        child, current = current, current.parentCtx
    return list(reversed(path))


def rule_name(context):
    return JavaParser.ruleNames[context.getRuleIndex()]
