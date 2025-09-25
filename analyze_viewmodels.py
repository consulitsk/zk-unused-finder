import os
import javalang
import argparse
import xml.etree.ElementTree as ET
import re
from collections import defaultdict
import json
import difflib

CACHE_FILE = ".viewmodel_analysis_cache.json"
resolved_constants = {}
VERBOSE = False
IGNORED_ANNOTATIONS = set()
ALL_PROJECT_FILES = []

def log_debug(message):
    """Prints a debug message if verbose mode is enabled."""
    if VERBOSE:
        print(f"[DEBUG] {message}")

def load_ignored_annotations(filepath="annotations.txt"):
    """Loads the set of annotations to ignore from a file."""
    global IGNORED_ANNOTATIONS
    if not os.path.exists(filepath):
        log_debug(f"Annotation file not found at '{filepath}'. No annotations will be ignored.")
        return
    try:
        with open(filepath, 'r') as f:
            IGNORED_ANNOTATIONS = {line.strip() for line in f if line.strip() and not line.startswith('#')}
        log_debug(f"Loaded {len(IGNORED_ANNOTATIONS)} annotations to ignore from '{filepath}': {IGNORED_ANNOTATIONS}")
    except IOError as e:
        print(f"Warning: Could not read annotation file '{filepath}': {e}")

def load_cache():
    """Loads the user decision cache from a file."""
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}

def save_cache(cache):
    """Saves the user decision cache to a file."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except IOError:
        print(f"Warning: Could not save cache to {CACHE_FILE}")

# Data Structures and Java Parser (no changes)
class MethodInfo:
    def __init__(self, name, annotations_text, line, block_start_line, imports, pkg):
        self.name, self.annotations_text, self.line = name, annotations_text, line
        self.block_start_line = block_start_line
        self.imports = imports
        self.pkg = pkg
        self.command_name = self._extract_command_name()
        self.used_in_java, self.used_in_zul = False, False
    def _extract_command_name(self):
        for ann_str in self.annotations_text:
            log_debug(f"  Parsing annotation for command: {ann_str}")
            if match := re.search(r'@(?:Global|Default)?Command\((.*)\)', ann_str):
                content = match.group(1).strip()
                log_debug(f"    Found command content: {content}")
                if content.startswith('"') and content.endswith('"'):
                    resolved_name = content.strip('"')
                    log_debug(f"    Resolved as string literal: '{resolved_name}'")
                    return resolved_name
                else:
                    log_debug(f"    Attempting to resolve as constant: {content}")
                    # Assume it's a constant like `SomeClass.NAME`
                    parts = content.split('.')
                    if len(parts) >= 2: # Handle FQDNs in constants
                        class_name = parts[-2]
                        const_name = parts[-1]
                        # Resolve FQDN of class_name
                        class_path = '.'.join(parts[:-1])
                        fqdn = self.imports.get(class_name, self.imports.get(class_path, f"{self.pkg}.{class_path}"))
                        const_fqdn = f"{fqdn}.{const_name}"
                        log_debug(f"    Looking for constant FQDN: {const_fqdn}")
                        resolved_name = resolved_constants.get(const_fqdn)
                        log_debug(f"    Resolved constant value: '{resolved_name}'")
                        return resolved_name
        return None
    def is_used(self):
        for ann_text in self.annotations_text:
            if any(ann_text.startswith(ignored) for ignored in IGNORED_ANNOTATIONS):
                log_debug(f"    Method '{self.name}' is ignored due to annotation: {ann_text}")
                return True
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

def extract_constants_from_ast(tree):
    pkg = tree.package.name if tree.package else ""
    for _, cls in tree.filter(javalang.tree.ClassDeclaration):
        cls_fqdn = f"{pkg}.{cls.name}" if pkg else cls.name
        for const in cls.fields:
            if 'public' in const.modifiers and 'static' in const.modifiers and 'final' in const.modifiers:
                # Check for String type, which might be BasicType or ReferenceType
                const_type = const.type
                is_string = False
                if isinstance(const_type, javalang.tree.BasicType) and const_type.name == 'String':
                    is_string = True
                elif isinstance(const_type, javalang.tree.ReferenceType) and const_type.name == 'String':
                    is_string = True

                if is_string:
                    for declarator in const.declarators:
                        if isinstance(declarator.initializer, javalang.tree.Literal):
                            value = declarator.initializer.value.strip('"')
                            const_fqdn = f"{cls_fqdn}.{declarator.name}"
                            resolved_constants[const_fqdn] = value
                            log_debug(f"Found constant: {const_fqdn} = '{value}'")

def extract_viewmodels_from_ast(tree, lines, file_path):
    vms = {}; pkg = tree.package.name if tree.package else ""; imports = {i.path.split('.')[-1]: i.path for i in tree.imports}
    log_debug(f"Parsing Java file for ViewModels: {file_path}")
    for _, cls in tree.filter(javalang.tree.ClassDeclaration):
        if not cls.name.endswith("ViewModel"): continue
        fqdn = f"{pkg}.{cls.name}" if pkg else cls.name
        ext_fqdn = None
        if cls.extends: ext_fqdn = imports.get(cls.extends.name, f"{pkg}.{cls.extends.name}")
        vm_info = ViewModelInfo(cls.name, fqdn, file_path, ext_fqdn)
        log_debug(f"Found ViewModel: {fqdn} (extends {ext_fqdn})")
        for meth in cls.methods:
            if 'public' in meth.modifiers:
                anns = []
                block_start_line = meth.position.line
                if meth.annotations:
                    block_start_line = meth.annotations[0].position.line
                    raw_anns = get_raw_text(lines, meth.annotations[0].position, (meth.position.line, meth.position.column))
                    anns = [a.strip() for a in raw_anns.split('\n') if a.strip().startswith('@')]
                vm_info.methods[meth.name] = MethodInfo(meth.name, anns, meth.position.line, block_start_line, imports, pkg)
                log_debug(f"  Found method: {meth.name} with annotations {anns}")
        vms[fqdn] = vm_info
    return vms

def analyze_java_files(project_path):
    vms, asts = {}, {}
    java_files = []
    log_debug(f"Starting Java file analysis in: {project_path}")
    for root, _, files in os.walk(project_path):
        for file in files:
            if file.endswith(".java"):
                java_files.append(os.path.join(root, file))

    log_debug(f"Found {len(java_files)} Java files to analyze.")
    for path in java_files:
        tree, lines = parse_java_file(path)
        if tree:
            asts[path] = tree
            log_debug(f"Extracting constants from: {path}")
            extract_constants_from_ast(tree)

    for path, tree in asts.items():
         _, lines = parse_java_file(path)
         vms.update(extract_viewmodels_from_ast(tree, lines, path))

    return vms, asts

# --- ZUL Parser (4th and Final Rewrite) ---
ZUL_VM_ID_REGEX = re.compile(r"@id\('([^']*)'\)")
ZUL_VM_INIT_REGEX = re.compile(r"@init\('([^']*)'\)")
COMMAND_REGEX = re.compile(r"""@(?:global-)?command\(['"]([^'"]*)['"][,)]""")
MEMBER_ACCESS_REGEX = re.compile(r"([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)")

def find_zul_usages_recursive(file_path, webapp_root, all_usages, partial_match, parent_context=None, visited=None):
    if visited is None: visited = set()
    abs_path = os.path.abspath(file_path)
    if abs_path in visited: return
    visited.add(abs_path)
    log_debug(f"Parsing ZUL file: {file_path}")

    try:
        tree = ET.parse(file_path)
        xml_root = tree.getroot()
    except (ET.ParseError, FileNotFoundError):
        log_debug(f"  Could not parse ZUL file.")
        return

    # Build parent map for context lookup
    parent_map = {c: p for p in xml_root.iter() for c in p}

    local_vm_map = {}
    has_local_vm = False
    for elem in xml_root.iter():
        vm_attrib = elem.attrib.get('viewModel')
        if vm_attrib:
            log_debug(f"  Found viewModel attribute: {vm_attrib}")
            has_local_vm = True
            id_m, init_m = ZUL_VM_ID_REGEX.search(vm_attrib), ZUL_VM_INIT_REGEX.search(vm_attrib)
            if id_m and init_m:
                alias, fqdn = id_m.group(1), init_m.group(1)
                local_vm_map[alias] = fqdn
                all_usages[fqdn].add(fqdn)
                log_debug(f"  Mapped local alias '{alias}' to FQDN '{fqdn}'")

    context_for_this_file = local_vm_map if has_local_vm else parent_context
    log_debug(f"  Using context map for this ZUL: {context_for_this_file}")

    for elem in xml_root.iter():
        # Scan attributes
        for attr_name, value in elem.attrib.items():
            log_debug(f"    Scanning element <{elem.tag}>, attribute '{attr_name}', value: \"{value}\"")
            # Commands - find context by walking up the tree
            for cmd in COMMAND_REGEX.findall(value):
                log_debug(f"      Found command match: '{cmd}'")
                curr = elem
                while curr in parent_map:
                    if vm_attrib := curr.attrib.get('viewModel'):
                        if id_m := ZUL_VM_ID_REGEX.search(vm_attrib):
                            alias = id_m.group(1)
                            if context_for_this_file and alias in context_for_this_file:
                                all_usages[context_for_this_file[alias]].add(cmd)
                                log_debug(f"        Added command usage '{cmd}' to {context_for_this_file[alias]}")
                                break
                    curr = parent_map[curr]
                else: # Fallback for root element or no context found
                    if context_for_this_file and 'vm' in context_for_this_file:
                        all_usages[context_for_this_file['vm']].add(cmd)
                        log_debug(f"        Added command usage '{cmd}' to {context_for_this_file['vm']} (fallback)")
            # Member access
            for alias, member in MEMBER_ACCESS_REGEX.findall(value):
                log_debug(f"      Found member access match: alias='{alias}', member='{member}'")
                if context_for_this_file and alias in context_for_this_file:
                    all_usages[context_for_this_file[alias]].add(member.split('.')[0])
                    log_debug(f"        Added member usage '{member}' to {context_for_this_file[alias]}")

        # Scan text and zscript
        scan_text = (elem.text or "") + (elem.find('.//zscript').text if elem.find('.//zscript') is not None and elem.find('.//zscript').text else "")
        if scan_text.strip():
            log_debug(f"    Scanning text/zscript content of <{elem.tag}>")
            for alias, member in MEMBER_ACCESS_REGEX.findall(scan_text):
                log_debug(f"      Found member access match in text: alias='{alias}', member='{member}'")
                if alias in context_for_this_file:
                    all_usages[context_for_this_file[alias]].add(member)
                    log_debug(f"        Added member usage '{member}' to {context_for_this_file[alias]}")

    # Handle includes
    for include in xml_root.iter('include'):
        if src := include.attrib.get('src'):
            log_debug(f"  Found include, recursing into: {src}")

            # Heuristic for dynamic includes
            if partial_match and '${' in src:
                log_debug(f"    Dynamic include detected. Applying partial match heuristic.")
                # Extract the static part of the filename
                static_part = re.sub(r'\$\{.*?\}', '', src).lstrip('/')
                log_debug(f"    Searching for files ending with: '{static_part}'")

                found_matches = False
                for proj_file in ALL_PROJECT_FILES:
                    if proj_file.endswith(static_part):
                        log_debug(f"      Found partial match: {proj_file}. Analyzing.")
                        find_zul_usages_recursive(proj_file, webapp_root, all_usages, partial_match, context_for_this_file, visited)
                        found_matches = True
                if not found_matches:
                    log_debug(f"      No partial matches found for '{static_part}'.")
                continue

            if src.startswith('/'):
                # Path is relative to webapp root
                included_path = os.path.join(webapp_root, src.lstrip('/'))
            else:
                # Path is relative to the current file's directory
                current_dir = os.path.dirname(file_path)
                included_path = os.path.join(current_dir, src)

            # Normalize the path to handle ".." etc.
            included_path = os.path.normpath(included_path)
            find_zul_usages_recursive(included_path, webapp_root, all_usages, partial_match, context_for_this_file, visited)

def find_zul_usages(project_path, partial_match):
    all_usages = defaultdict(set)

    webapp_roots = []
    log_debug(f"Searching for 'webapp' directories in project root: {project_path}")
    for root, dirs, _ in os.walk(project_path):
        if 'webapp' in dirs and root.endswith(os.path.join('src', 'main')):
            webapp_roots.append(os.path.join(root, 'webapp'))

    if not webapp_roots:
        log_debug("No 'src/main/webapp' directories found.")
        return all_usages

    log_debug(f"Found {len(webapp_roots)} webapp root(s): {webapp_roots}")

    for webapp_root in webapp_roots:
        log_debug(f"Analyzing ZULs in: {webapp_root}")
        for root, _, files in os.walk(webapp_root):
            for file in files:
                if file.endswith(".zul"):
                    file_path = os.path.join(root, file)
                    find_zul_usages_recursive(file_path, webapp_root, all_usages, partial_match)

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
    log_debug(f"--- Starting Final Analysis Phase ---")
    log_debug(f"ZUL Usages Found: {dict(zul_usages)}")
    for fqdn, names in zul_usages.items():
        if fqdn in view_models:
            log_debug(f"Processing ZUL usages for ViewModel: {fqdn}")
            view_models[fqdn].is_used_in_zul = True
            for name in names:
                log_debug(f"  Processing usage '{name}'")
                curr_fqdn = fqdn
                while curr_fqdn in view_models:
                    vm, found = view_models[curr_fqdn], False
                    for meth in vm.methods.values():
                        if meth.name == name or meth.command_name == name:
                            meth.used_in_zul = True; found = True
                            log_debug(f"    Marking '{meth.name}' as used in ZUL (direct or command match)")
                        getter, setter, is_getter = f"get{name[0].upper()}{name[1:]}", f"set{name[0].upper()}{name[1:]}", f"is{name[0].upper()}{name[1:]}"
                        if meth.name in (getter, setter, is_getter):
                            meth.used_in_zul = True
                            log_debug(f"    Marking '{meth.name}' as used in ZUL (getter/setter match for '{name}')")
                    if found: break
                    curr_fqdn = vm.extends
    log_debug("--- Propagating usage status up the inheritance chain ---")
    for fqdn, vm in view_models.items():
        parent_fqdn = vm.extends
        while parent_fqdn in view_models:
            parent_vm = view_models[parent_fqdn]
            for meth_name, meth_info in vm.methods.items():
                if (meth_info.used_in_java or meth_info.used_in_zul) and meth_name in parent_vm.methods:
                    parent_vm.methods[meth_name].used_in_java |= meth_info.used_in_java
                    parent_vm.methods[meth_name].used_in_zul |= meth_info.used_in_zul
            parent_fqdn = parent_vm.extends

def get_unused_methods(view_models):
    """
    Analyzes view_models and returns a list of tuples, where each tuple contains
    a ViewModelInfo object and a list of its unused MethodInfo objects.
    """
    used_vms_with_issues = []
    log_debug("--- Identifying unused methods ---")
    for fqdn, vm in sorted(view_models.items()):
        log_debug(f"Checking ViewModel: {fqdn}")
        if not vm.is_used():
            log_debug(f"  ViewModel is completely unused.")
            continue

        unused_meths = []
        for meth in sorted(vm.methods.values(), key=lambda m: m.line):
            is_used_result = meth.is_used()
            if not is_used_result:
                log_debug(f"  Method '{meth.name}' is UNUSED. Reason: used_in_java={meth.used_in_java}, used_in_zul={meth.used_in_zul}, annotations={meth.annotations_text}")
                unused_meths.append(meth)
            else:
                log_debug(f"  Method '{meth.name}' is USED.")

        if unused_meths:
            used_vms_with_issues.append((vm, unused_meths))
    return used_vms_with_issues

def interactive_session(view_models):
    """
    Runs an interactive session to let the user decide which unused methods to delete.
    Returns a list of (ViewModelInfo, MethodInfo) tuples for approved deletions.
    """
    cache = load_cache()
    candidates = get_unused_methods(view_models)
    approved_for_deletion = []
    quit_session = False

    print("--- Interactive Deletion Session ---")
    print("For each method, enter 'y' to delete, 'n' to keep, or 'q' to quit.")

    for vm, unused_meths in candidates:
        if quit_session: break
        for meth in unused_meths:
            method_id = f"{vm.fqdn}#{meth.name}"

            if method_id in cache:
                if cache[method_id] == 'y':
                    # Still add to approved list if already approved in cache
                    approved_for_deletion.append((vm, meth))
                continue

            print("-" * 60)
            print(f"ViewModel: {vm.fqdn}")
            print(f"File:      {vm.file_path}:{meth.line}")
            print(f"Method:    {meth.name}")

            while True:
                try:
                    choice = input("Delete this method? (y/n/q): ").lower().strip()
                except (EOFError, KeyboardInterrupt):
                    choice = 'q'
                    print("\nSession interrupted.")

                if choice in ['y', 'n']:
                    cache[method_id] = choice
                    save_cache(cache)
                    if choice == 'y':
                        approved_for_deletion.append((vm, meth))
                    break
                elif choice == 'q':
                    print("Quitting interactive session.")
                    quit_session = True
                    break
                else:
                    print("Invalid input. Please enter 'y', 'n', or 'q'.")

    print("-" * 60)
    if not quit_session:
        print("All candidates have been reviewed.")

    # Filter out any duplicates that might have been added
    unique_approved = list(dict.fromkeys(approved_for_deletion))
    return unique_approved

def find_method_end_line(lines, start_line_idx):
    """
    Finds the end line of a method by counting braces.
    `lines` is a list of strings, `start_line_idx` is the 0-based index to start searching.
    """
    brace_count = 0
    in_block = False
    for i in range(start_line_idx, len(lines)):
        line = lines[i]
        if '{' in line and not in_block:
            in_block = True
        if in_block:
            brace_count += line.count('{')
            brace_count -= line.count('}')
        if in_block and brace_count == 0:
            return i + 1  # Return 1-based line number
    return start_line_idx + 1 # Fallback

def generate_patches(approved_methods):
    """
    Generates .patch files for the approved methods.
    """
    if not approved_methods:
        print("No methods approved for deletion. No patches generated.")
        return

    os.makedirs("patches", exist_ok=True)

    methods_by_file = defaultdict(list)
    for vm, meth in approved_methods:
        methods_by_file[vm.file_path].append(meth)

    for file_path, methods in methods_by_file.items():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                original_lines = f.readlines()
        except IOError as e:
            print(f"Error reading file {file_path}: {e}")
            continue

        methods.sort(key=lambda m: m.block_start_line, reverse=True)

        lines_to_delete = set()
        for meth in methods:
            start_idx = meth.block_start_line - 1
            end_idx = find_method_end_line(original_lines, start_idx) -1
            for i in range(start_idx, end_idx + 1):
                lines_to_delete.add(i)

        new_lines = [line for i, line in enumerate(original_lines) if i not in lines_to_delete]

        patch_file_name = os.path.join("patches", os.path.basename(file_path) + ".patch")
        try:
            with open(patch_file_name, 'w', encoding='utf-8') as f:
                diff = difflib.unified_diff(
                    original_lines,
                    new_lines,
                    fromfile=os.path.abspath(file_path),
                    tofile=os.path.abspath(file_path),
                )
                f.writelines(diff)
            print(f"Generated patch: {patch_file_name}")
        except IOError as e:
            print(f"Error writing patch file {patch_file_name}: {e}")


def generate_report(view_models):
    report = ["# Unused ViewModel Methods Report"]
    unused_vms = [vm for vm in sorted(view_models.values(), key=lambda v: v.fqdn) if not vm.is_used()]
    used_vms_with_issues = get_unused_methods(view_models)

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
    parser.add_argument("--interactive", action="store_true", help="Enable interactive mode to generate removal patches.")
    parser.add_argument("--reset-cache", action="store_true", help="Reset the cache of user decisions.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging for debugging.")
    parser.add_argument("--no-partial-match", action="store_false", dest="partial_match", help="Disable the heuristic for finding dynamic includes by partial name match.")
    args = parser.parse_args()

    global VERBOSE
    VERBOSE = args.verbose

    load_ignored_annotations()

    if args.reset_cache:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            print(f"Cache file {CACHE_FILE} has been reset.")
        else:
            print(f"No cache file ({CACHE_FILE}) to reset.")
        return

    print(f"Analyzing project: {args.project_path}...\n")
    log_debug("Caching all .zul file paths for partial match heuristic...")
    for root, _, files in os.walk(args.project_path):
        for file in files:
            if file.endswith(".zul"):
                ALL_PROJECT_FILES.append(os.path.join(root, file))
    log_debug(f"Cached {len(ALL_PROJECT_FILES)} .zul file paths.")

    vms, asts = analyze_java_files(args.project_path)
    zul_usages = find_zul_usages(args.project_path, args.partial_match)
    analyze_java_usages(asts, vms)
    run_analysis(vms, zul_usages)

    if args.interactive:
        approved_methods = interactive_session(vms)
        if approved_methods:
            print(f"\n{len(approved_methods)} methods approved for deletion.")
            generate_patches(approved_methods)
        else:
            print("\nNo new methods were approved for deletion.")
    else:
        report = generate_report(vms)
        print(report)
        with open("unused_viewmodel_report.md", "w") as f: f.write(report)
        print("\nReport saved to unused_viewmodel_report.md")

if __name__ == "__main__":
    main()
