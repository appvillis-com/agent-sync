## What and why

<!-- What changes, and what problem it solves. Link the issue if there is one. -->

## Evidence

<!-- Paste what you ran and what it printed. Both are required for any change. -->

```
python3 test/validate.py
```

## Checklist

- [ ] `python3 test/validate.py` passes
- [ ] Coordination changes were exercised against a real lease cycle, not only unit-level
- [ ] A new validator guard ships with a negative self-test that plants the defect and watches the check fail
- [ ] Behavior change is reflected in `README.md`
- [ ] `CHANGELOG.md` has an entry for this change
- [ ] If versions moved: `package.json`, `.claude-plugin/marketplace.json`, `plugins/agent-sync/.claude-plugin/plugin.json` and the top `CHANGELOG.md` heading all agree
