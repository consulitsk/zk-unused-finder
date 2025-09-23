import os
import javalang
import argparse
import xml.etree.ElementTree as ET
import re
from collections import defaultdict

# Data Structures and Java Parser (no changes)
class MethodInfo:
    def __init__(self, name, annotations_text, line):
        self.name, self.annotations_text, self.line = name, annotations_text, line
        self.command_name = self._extract_command_name()
        self.used_in_java, self.used_in_zul = False, False
    def _extract_command_name(self):
        for ann_str in self.annotations_text:
            if match := re.search(r'@(?:Global|Default)?Command\("([^"]*)"\)', ann_str): return match.group(1)
        return None
    def is_used(self):
        for ann_text in self.annotations_text:
            if any(ann_text.startswith(lifecycle_ann) for lifecycle_ann in ['@Init', '@AfterCompose', '@Destroy']): return True
        return self.used_in_java or self.used_in_zul

class ViewModelInfo:
    def __init__(self, name, fqdn, file_path, extends):
        self.name, self.fqdn, self.file_path, self.extends = name, fqdn, file_path, extends
        self.methods, self.is_used_in_zul, self.is_used_in_java = {}, False, False
    def is_used(self):
        if self.is_used_in_zul or self.is_used_in_java: return True
        return any(m.is_used() for m in self.methods.values())

def get_raw_text(content_lines, start_pos, end_pos):
    if not start_pos or not end_pos: return ""
    start_line, start_col, end_line, end_col = start_pos[0], start_pos[1], end_pos[0], end_pos[1]
    if start_line == end_line: return content_lines[start_line - 1][start_col - 1:end_col]
    text = content_lines[start_line - 1][start_col - 1:]
    for i in range(start_line, end_line - 1): text += content_lines[i]
    text += content_lines[end_line - 1][:end_col]; return text

def parse_java_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f: content = f.read()
        return javalang.parse.parse(content), content.splitlines()
    except Exception: return None, None

def extract_viewmodels_from_ast(tree, lines, file_path):
    vms = {}; pkg = tree.package.name if tree.package else ""; imports = {i.path.split('.')[-1]: i.path for i in tree.imports}
    for _, cls in tree.filter(javalang.tree.ClassDeclaration):
        if not cls.name.endswith("ViewModel"): continue
        fqdn = f"{pkg}.{cls.name}" if pkg else cls.name
        ext_fqdn = None
        if cls.extends: ext_fqdn = imports.get(cls.extends.name, f"{pkg}.{cls.extends.name}")
        vm_info = ViewModelInfo(cls.name, fqdn, file_path, ext_fqdn)
        for meth in cls.methods:
            if 'public' in meth.modifiers:
                anns = []
                if meth.annotations:
                    raw_anns = get_raw_text(lines, meth.annotations[0].position, (meth.position.line, meth.position.column))
                    anns = [a.strip() for a in raw_anns.split('\n') if a.strip().startswith('@')]
                vm_info.methods[meth.name] = MethodInfo(meth.name, anns, meth.position.line)
        vms[fqdn] = vm_info
    return vms

def analyze_java_files(project_path):
    vms, asts = {}, {}
    for root, _, files in os.walk(project_path):
        for file in files:
            if file.endswith(".java"):
                path = os.path.join(root, file)
                tree, lines = parse_java_file(path)
                if tree: asts[path] = tree; vms.update(extract_viewmodels_from_ast(tree, lines, path))
    return vms, asts

# --- ZUL Parser (4th and Final Rewrite) ---
ZUL_VM_ID_REGEX = re.compile(r"@id\('([^']*)'\)")
ZUL_VM_INIT_REGEX = re.compile(r"@init\('([^']*)'\)")
COMMAND_REGEX = re.compile(r"@(?:global-)?command\('([^']*)'[,)]")
MEMBER_ACCESS_REGEX = re.compile(r"([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)")

def find_zul_usages_recursive(file_path, webapp_root, all_usages, parent_context=None, visited=None):
    if visited is None: visited = set()
    abs_path = os.path.abspath(file_path)
    if abs_path in visited: return
    visited.add(abs_path)

    try:
        tree = ET.parse(file_path)
        xml_root = tree.getroot()
    except (ET.ParseError, FileNotFoundError): return

    # Build parent map for context lookup
    parent_map = {c: p for p in xml_root.iter() for c in p}

    local_vm_map = {}
    has_local_vm = False
    for elem in xml_root.iter():
        vm_attrib = elem.attrib.get('viewModel')
        if vm_attrib:
            has_local_vm = True
            id_m, init_m = ZUL_VM_ID_REGEX.search(vm_attrib), ZUL_VM_INIT_REGEX.search(vm_attrib)
            if id_m and init_m:
                alias, fqdn = id_m.group(1), init_m.group(1)
                local_vm_map[alias] = fqdn
                all_usages[fqdn].add(fqdn)

    context_map = local_vm_map if has_local_vm or not parent_context else parent_context

    for elem in xml_root.iter():
        # Scan attributes
        for _, value in elem.attrib.items():
            # Commands - find context by walking up the tree
            for cmd in COMMAND_REGEX.findall(value):
                curr = elem
                while curr in parent_map:
                    if vm_attrib := curr.attrib.get('viewModel'):
                        if id_m := ZUL_VM_ID_REGEX.search(vm_attrib):
                            alias = id_m.group(1)
                            if alias in context_map:
                                all_usages[context_map[alias]].add(cmd)
                                break
                    curr = parent_map[curr]
                else: # Fallback for root element or no context found
                    if 'vm' in context_map: all_usages[context_map['vm']].add(cmd)
            # Member access
            for alias, member in MEMBER_ACCESS_REGEX.findall(value):
                if alias in context_map: all_usages[context_map[alias]].add(member.split('.')[0])

        # Scan text and zscript
        scan_text = (elem.text or "") + (elem.find('.//zscript').text if elem.find('.//zscript') is not None and elem.find('.//zscript').text else "")
        for alias, member in MEMBER_ACCESS_REGEX.findall(scan_text):
            if alias in context_map: all_usages[context_map[alias]].add(member)

    # Handle includes
    for include in xml_root.iter('include'):
        if src := include.attrib.get('src'):
            included_path = os.path.join(webapp_root, src.lstrip('/'))
            find_zul_usages_recursive(included_path, webapp_root, all_usages, context_map, visited)

def find_zul_usages(project_path):
    all_usages = defaultdict(set)
    webapp_root = os.path.join(project_path, 'src', 'main', 'webapp')
    if not os.path.isdir(webapp_root): return all_usages
    for root, _, files in os.walk(webapp_root):
        for file in files:
            if file.endswith(".zul"):
                file_path = os.path.join(root, file)
                find_zul_usages_recursive(file_path, webapp_root, all_usages)
    return all_usages

# --- Java Usage Analyzer & Reporting (Unchanged) ---
def analyze_java_usages(asts, view_models):
    for _, tree in asts.items():
        var_types, imports, pkg = {}, {i.path.split('.')[-1]: i.path for i in tree.imports}, tree.package.name if tree.package else ""
        for _, lvd in tree.filter(javalang.tree.LocalVariableDeclaration):
            fqdn = imports.get(lvd.type.name, f"{pkg}.{lvd.type.name}")
            if fqdn in view_models:
                for decl in lvd.declarators: var_types[decl.name] = fqdn
        for _, inv in tree.filter(javalang.tree.MethodInvocation):
            if isinstance(inv.qualifier, str) and inv.qualifier in var_types:
                vm_fqdn, meth_name = var_types[inv.qualifier], inv.member
                if vm_fqdn in view_models and meth_name in view_models[vm_fqdn].methods:
                    view_models[vm_fqdn].methods[meth_name].used_in_java = True
                    view_models[vm_fqdn].is_used_in_java = True
        for _, cr in tree.filter(javalang.tree.ClassCreator):
            fqdn = imports.get(cr.type.name, f"{pkg}.{cr.type.name}")
            if fqdn in view_models: view_models[fqdn].is_used_in_java = True

def run_analysis(view_models, zul_usages):
    for fqdn, names in zul_usages.items():
        if fqdn in view_models:
            view_models[fqdn].is_used_in_zul = True
            for name in names:
                curr_fqdn = fqdn
                while curr_fqdn in view_models:
                    vm, found = view_models[curr_fqdn], False
                    for meth in vm.methods.values():
                        if meth.name == name or meth.command_name == name: meth.used_in_zul = True; found = True
                        getter, setter, is_getter = f"get{name[0].upper()}{name[1:]}", f"set{name[0].upper()}{name[1:]}", f"is{name[0].upper()}{name[1:]}"
                        if meth.name in (getter, setter, is_getter): meth.used_in_zul = True
                    if found: break
                    curr_fqdn = vm.extends
    for fqdn, vm in view_models.items():
        parent_fqdn = vm.extends
        while parent_fqdn in view_models:
            parent_vm = view_models[parent_fqdn]
            for meth_name, meth_info in vm.methods.items():
                if (meth_info.used_in_java or meth_info.used_in_zul) and meth_name in parent_vm.methods:
                    parent_vm.methods[meth_name].used_in_java |= meth_info.used_in_java
                    parent_vm.methods[meth_name].used_in_zul |= meth_info.used_in_zul
            parent_fqdn = parent_vm.extends

def generate_report(view_models):
    report = ["# Unused ViewModel Methods Report"]
    unused_vms, used_vms_with_issues = [], []
    for fqdn, vm in sorted(view_models.items()):
        if not vm.is_used(): unused_vms.append(vm); continue
        unused_meths = [meth for meth in sorted(vm.methods.values(), key=lambda m: m.line) if not meth.is_used()]
        if unused_meths: used_vms_with_issues.append((vm, unused_meths))
    if unused_vms:
        report.append("\n## Completely Unused ViewModels\n")
        for vm in unused_vms: report.append(f"- **{vm.fqdn}** (at `{vm.file_path}`)")
    if used_vms_with_issues:
        report.append("\n## Unused Methods in Active ViewModels\n")
        for vm, meths in used_vms_with_issues:
            report.append(f"\n### ViewModel: `{vm.fqdn}`")
            for meth in meths: report.append(f"- Method: `{meth.name}` (line {meth.line})")
    if not unused_vms and not used_vms_with_issues:
        report.append("\nCongratulations! No unused ViewModel classes or methods were found.")
    return "\n".join(report)

def main():
    parser = argparse.ArgumentParser(description="Analyze ZK project for unused ViewModel methods.")
    parser.add_argument("project_path", help="Path to the root of the Java project.")
    args = parser.parse_args()
    print(f"Analyzing project: {args.project_path}...\n")
    vms, asts = analyze_java_files(args.project_path)
    zul_usages = find_zul_usages(args.project_path)
    analyze_java_usages(asts, vms)
    run_analysis(vms, zul_usages)
    report = generate_report(vms)
    print(report)
    with open("unused_viewmodel_report.md", "w") as f: f.write(report)
    print("\nReport saved to unused_viewmodel_report.md")

if __name__ == "__main__":
    main()
