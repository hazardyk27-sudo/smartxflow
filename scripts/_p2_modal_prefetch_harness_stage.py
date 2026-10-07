from pathlib import Path

path = Path('tests/test_app_bootstrap.js')
text = path.read_text(encoding='utf-8')
old = '_startBackgroundLiveFetch() {},\n'
new = '_startBackgroundLiveFetch() {},\n    scheduleDeferredModalRuntimePrefetch() {},\n'
count = text.count(old)
if count < 2:
    raise SystemExit(f'expected at least two bootstrap live-fetch stubs, got {count}')
if 'scheduleDeferredModalRuntimePrefetch() {}' in text:
    raise SystemExit('modal prefetch bootstrap stub already present')
text = text.replace(old, new)
path.write_text(text, encoding='utf-8')
print(f'updated bootstrap harness contexts: {count}')
