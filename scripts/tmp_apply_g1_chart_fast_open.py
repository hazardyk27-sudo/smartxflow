from pathlib import Path
import re


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 replacement, found {count}")
    return text.replace(old, new, 1)


# 1) Keep export-only html2canvas out of the first chart-open dependency chain.
src_path = Path("static/js/app.js.src")
src = src_path.read_text()
old_plugins = """        var pluginScripts = [
            'https://cdn.jsdelivr.net/npm/hammerjs@2.0.8',
            'https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js'
        ];"""
new_plugins = """        var pluginScripts = [
            'https://cdn.jsdelivr.net/npm/hammerjs@2.0.8'
        ];"""
src = replace_once(src, old_plugins, new_plugins, "source chart plugins")

old_export = """async function exportChartPNG(...args) {
    await loadChartExportRuntime();
    return window.__sxfExportChartPNGImpl(...args);
}"""
new_export = """let _html2CanvasExportPromise = null;
function loadHtml2CanvasForExport() {
    if (typeof html2canvas === 'function') return Promise.resolve();
    if (_html2CanvasExportPromise) return _html2CanvasExportPromise;
    _html2CanvasExportPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js';
        script.async = true;
        script.onload = () => resolve();
        script.onerror = () => {
            _html2CanvasExportPromise = null;
            reject(new Error('html2canvas failed to load'));
        };
        document.head.appendChild(script);
    });
    return _html2CanvasExportPromise;
}

async function exportChartPNG(...args) {
    await loadChartExportRuntime();
    await loadHtml2CanvasForExport();
    return window.__sxfExportChartPNGImpl(...args);
}"""
src = replace_once(src, old_export, new_export, "source PNG export wrapper")
src_path.write_text(src)

runtime_path = Path("static/js/app.js")
runtime = runtime_path.read_text()
old_plugins_rt = "var pluginScripts=['https://cdn.jsdelivr.net/npm/hammerjs@2.0.8','https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js'];"
new_plugins_rt = "var pluginScripts=['https://cdn.jsdelivr.net/npm/hammerjs@2.0.8'];"
runtime = replace_once(runtime, old_plugins_rt, new_plugins_rt, "runtime chart plugins")
export_pattern = re.compile(r"async function exportChartPNG\(\.\.\.args\)\{await loadChartExportRuntime\(\);return window\.__sxfExportChartPNGImpl\(\.\.\.args\);\}")
if len(list(export_pattern.finditer(runtime))) != 1:
    raise SystemExit("runtime PNG export wrapper: expected exactly one match")
export_rt = "let _html2CanvasExportPromise=null;function loadHtml2CanvasForExport(){if(typeof html2canvas==='function')return Promise.resolve();if(_html2CanvasExportPromise)return _html2CanvasExportPromise;_html2CanvasExportPromise=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js';script.async=true;script.onload=()=>resolve();script.onerror=()=>{_html2CanvasExportPromise=null;reject(new Error('html2canvas failed to load'));};document.head.appendChild(script);});return _html2CanvasExportPromise;}async function exportChartPNG(...args){await loadChartExportRuntime();await loadHtml2CanvasForExport();return window.__sxfExportChartPNGImpl(...args);}"
runtime = export_pattern.sub(export_rt, runtime, count=1)
runtime_path.write_text(runtime)

# 2) First chart open fetches only the selected market, not all six histories.
for path_str, minified in [("static/js/modal-entry.js.src", False), ("static/js/modal-entry.js", True)]:
    p = Path(path_str)
    text = p.read_text()
    if minified:
        text, removed = re.subn(r"const marketsPromise=loadAllMarketsAtOnce\([^;]+\);", "", text)
        text, replaced = re.subn(r"Promise\.all\(\[marketsPromise,chartLibsPromise\]\)\.then", "chartLibsPromise.then", text)
    else:
        text, removed = re.subn(r"^[ \t]*const marketsPromise = loadAllMarketsAtOnce\([^\n]+\);\n", "", text, flags=re.M)
        text, replaced = re.subn(r"Promise\.all\(\[marketsPromise, chartLibsPromise\]\)\.then", "chartLibsPromise.then", text)
    if removed != 3 or replaced != 3:
        raise SystemExit(f"{path_str}: expected 3 bulk removals + 3 pipeline replacements, got {removed}/{replaced}")
    p.write_text(text)

# 3) Lock behavior in existing canonical frontend performance coverage.
test_path = Path("tests/test_deferred_chart_libs.js")
test = test_path.read_text()
anchor = """    assert.doesNotMatch(bootstrap, /chart libraries/);
  });"""
addition = """    assert.doesNotMatch(bootstrap, /chart libraries/);
  });

  test(`first chart-open loader excludes export-only html2canvas (${name})`, () => {
    const start = source.indexOf('window.loadChartLibs');
    const end = source.indexOf('let currentMarket', start);
    assert.ok(start >= 0 && end > start, 'chart loader boundary should exist');
    const loader = source.slice(start, end);
    assert.doesNotMatch(loader, /html2canvas/);
    assert.match(source, /loadHtml2CanvasForExport/);
  });"""
test = replace_once(test, anchor, addition, "chart loader regression test")
anchor2 = """      assert.match(fn, /registerChartPlugins/);
    });"""
addition2 = """      assert.match(fn, /registerChartPlugins/);
      assert.doesNotMatch(fn, /loadAllMarketsAtOnce/);
      assert.doesNotMatch(fn, /marketsPromise/);
    });"""
test = replace_once(test, anchor2, addition2, "selected-market modal regression test")
test_path.write_text(test)
