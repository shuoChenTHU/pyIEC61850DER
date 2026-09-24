import os
import ast
import re
import pathspec


def get_module_info(filepath):
    """Returns the first line (summary) from a python module docstring."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
            doc = ast.get_docstring(tree)
            if doc:
                lines = [line.strip() for line in doc.split('\n') if line.strip()]
                if lines:
                    return lines[0]
    except Exception:
        pass
    return ""


def get_readme_summary(dir_path):
    """Finds a README.md file (case-insensitive) and extracts its first heading/line."""
    try:
        # Search case-insensitively for readme.md files
        for filename in os.listdir(dir_path):
            if filename.lower() == "readme.md":
                readme_path = os.path.join(dir_path, filename)
                if os.path.isfile(readme_path):
                    with open(readme_path, "r", encoding="utf-8") as f:
                        for line in f:
                            cleaned = line.strip()
                            if cleaned:
                                # Strip out Markdown heading syntax if present (e.g. # Summary -> Summary)
                                return re.sub(r'^#+\s*', '', cleaned)
    except Exception:
        pass
    return ""


def load_git_spec(treeignore_path=".treeignore"):
    """Loads and compiles rules from a .treeignore file into a PathSpec object."""
    if os.path.exists(treeignore_path):
        with open(treeignore_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, lines)

    print(f"Warning: {treeignore_path} not found. No files will be filtered.")
    return pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, [])


def generate_tree(path, spec, base_root, indent=""):
    infra_ignore = {'.git', '.idea'}

    try:
        raw_items = os.listdir(path)
    except PermissionError:
        return

    items = sorted([i for i in raw_items if i not in infra_ignore])
    filtered_items = []

    # Pre-filter items based on treeignore specifications
    for item in items:
        full_path = os.path.join(path, item)
        rel_path = os.path.relpath(full_path, base_root).replace("\\", "/")

        if os.path.isdir(full_path):
            rel_path += "/"

        if not spec.match_file(rel_path):
            filtered_items.append((item, full_path))

    # Construct and print out the visible hierarchy
    for i, (item, full_path) in enumerate(filtered_items):
        is_last = (i == len(filtered_items) - 1)
        prefix = "└── " if is_last else "├── "

        description = ""
        if item.endswith(".py"):
            summary = get_module_info(full_path)
            if summary:
                description = f"  # {summary}"
        elif os.path.isdir(full_path):
            # 1. Primary check: Try to extract summary from a case-insensitive README.md file
            summary = get_readme_summary(full_path)

            # 2. Secondary fallback: Look for __init__.py docstring if no README exists
            if not summary:
                init_path = os.path.join(full_path, "__init__.py")
                if os.path.exists(init_path):
                    summary = get_module_info(init_path)

            if summary:
                description = f"  # {summary}"

        print(f"{indent}{prefix}{item}{description}")

        if os.path.isdir(full_path):
            extension = "    " if is_last else "│   "
            generate_tree(full_path, spec, base_root, indent + extension)


if __name__ == "__main__":
    os.chdir('../')
    outer_root = os.path.abspath(os.getcwd())
    inner_root = os.path.join(outer_root, "pyiec61850der")

    treeignore_path = os.path.normpath(os.path.join(outer_root, 'doc', '.treeignore'))
    git_spec = load_git_spec(treeignore_path)

    print(f"pyiec61850der\\")
    generate_tree(inner_root, git_spec, base_root=outer_root)
