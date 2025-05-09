import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk
import re
import os

# --- Utility Functions (no changes from previous) ---
def get_line_col_from_pos(text, pos):
    if pos > len(text): pos = len(text)
    line_num = text.count('\n', 0, pos) + 1
    prev_newline_pos = text.rfind('\n', 0, pos)
    col_num = pos - prev_newline_pos if prev_newline_pos != -1 else pos + 1
    return line_num, col_num

def get_context_line_from_pos(text, pos):
    if pos > len(text): pos = len(text)
    start_of_line = text.rfind('\n', 0, pos) + 1
    end_of_line = text.find('\n', pos)
    if end_of_line == -1: end_of_line = len(text)
    return text[start_of_line:end_of_line]

def is_in_comment_on_line(text_content, char_to_check_pos, search_start_offset=0):
    line_start_pos = text_content.rfind('\n', 0, char_to_check_pos) + 1
    current_search_offset_abs = line_start_pos
    while current_search_offset_abs < char_to_check_pos:
        try:
            comment_char_abs_pos = text_content.index('%', current_search_offset_abs, char_to_check_pos)
        except ValueError:
            return False
        num_backslashes = 0
        temp_idx = comment_char_abs_pos - 1
        while temp_idx >= line_start_pos and text_content[temp_idx] == '\\':
            num_backslashes += 1
            temp_idx -= 1
        if num_backslashes % 2 == 0:
            return True 
        current_search_offset_abs = comment_char_abs_pos + 1
    return False

# --- Core Logic Function ---
def find_target_char_in_tex(filepath, target_char_str, ignore_text_commands_flag, search_mode):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return {"error_message": f"Error reading file: {e}", "issues_list": [], "searched_char": target_char_str}

    if not target_char_str:
        return {"error_message": "Target character is empty.", "issues_list": [], "searched_char": target_char_str}

    issues_found = []
    escaped_target_char = re.escape(target_char_str)
    target_pattern = re.compile(escaped_target_char)

    env_pattern = re.compile(
        r"\\begin\{(?P<env_name>(?:equation|align|gather|multline|eqnarray|displaymath|math|subequations)\*?)\}"
        r"(?P<env_content>(?:.|\n)*?)"
        r"\\end\{(?P=env_name)\}",
        re.DOTALL
    )
    bracket_pattern = re.compile(r"\\\[(?P<bracket_content>(?:.|\n)*?)\\\]", re.DOTALL)
    double_dollar_pattern = re.compile(r"(?<!\\)\$\$(?P<doubledollar_content>(?:.|\n)*?)(?<!\\)\$\$", re.DOTALL)
    inline_pattern = re.compile(r"(?<![\$\\])\$(?P<inline_content>(?:[^$\\]|\\.)*?)(?<!\\)\$")
    
    math_env_regexes = [
        {"pattern": env_pattern, "content_group": "env_content", "type_group": "env_name", "is_block": True},
        {"pattern": bracket_pattern, "content_group": "bracket_content", "type_value": "display math \\[\\]", "is_block": True},
        {"pattern": double_dollar_pattern, "content_group": "doubledollar_content", "type_value": "display math $$", "is_block": True},
        {"pattern": inline_pattern, "content_group": "inline_content", "type_value": "inline math $", "is_block": False},
    ]

    if search_mode == "math_only":
        for config in math_env_regexes:
            pattern = config["pattern"]
            for match in pattern.finditer(content):
                math_content_inner = match.group(config["content_group"])
                math_content_inner_start_offset = match.start(config["content_group"])
                env_type_str = config.get("type_value")
                if "type_group" in config: env_type_str = match.group(config["type_group"])

                for char_match in target_pattern.finditer(math_content_inner):
                    target_relative_pos_in_inner = char_match.start()
                    target_absolute_pos = math_content_inner_start_offset + target_relative_pos_in_inner
                    if is_in_comment_on_line(content, target_absolute_pos, match.start()):
                        continue
                    # ignore_text_commands_flag handling (not fully implemented)
                    if ignore_text_commands_flag:
                        pass 

                    line_num, col_num = get_line_col_from_pos(content, target_absolute_pos)
                    context_line_text = get_context_line_from_pos(content, target_absolute_pos)
                    issues_found.append({
                        "file": filepath, "line": line_num, "col": col_num,
                        "type": f"Math ({env_type_str})", "context": context_line_text.strip(),
                        "char_pos": target_absolute_pos, "detected_char": char_match.group(0)
                    })

    elif search_mode == "document_wide":
        for char_match in target_pattern.finditer(content):
            target_absolute_pos = char_match.start()
            if is_in_comment_on_line(content, target_absolute_pos):
                 continue
            line_num, col_num = get_line_col_from_pos(content, target_absolute_pos)
            context_line_text = get_context_line_from_pos(content, target_absolute_pos)
            issues_found.append({
                "file": filepath, "line": line_num, "col": col_num,
                "type": "Text (Document-wide)",
                "context": context_line_text.strip(),
                "char_pos": target_absolute_pos, "detected_char": char_match.group(0)
            })
    
    elif search_mode == "text_only_strict":
        math_spans = []
        for config in math_env_regexes:
            for match in config["pattern"].finditer(content):
                math_spans.append((match.start(), match.end()))
        math_spans.sort() 
        
        for char_match in target_pattern.finditer(content):
            target_absolute_pos = char_match.start()
            target_end_pos = char_match.end()

            if is_in_comment_on_line(content, target_absolute_pos):
                 continue

            in_math = False
            for start, end in math_spans:
                if max(target_absolute_pos, start) < min(target_end_pos, end):
                    in_math = True
                    break
            
            if not in_math:
                line_num, col_num = get_line_col_from_pos(content, target_absolute_pos)
                context_line_text = get_context_line_from_pos(content, target_absolute_pos)
                issues_found.append({
                    "file": filepath, "line": line_num, "col": col_num,
                    "type": "Text (Outside Math)",
                    "context": context_line_text.strip(),
                    "char_pos": target_absolute_pos, "detected_char": char_match.group(0)
                })

    unique_issues = []
    seen_positions = set()
    issues_found.sort(key=lambda x: (x['char_pos'], x.get('detected_char','')))
    for issue in issues_found:
        issue_key = (issue['char_pos'], issue.get('detected_char',''))
        if issue_key not in seen_positions:
            unique_issues.append(issue)
            seen_positions.add(issue_key)
            
    return {"error_message": None, "issues_list": unique_issues, "searched_char": target_char_str}

# --- GUI Application Class ---
class TexCharCheckerApp:
    def __init__(self, root_window):
        self.root_window = root_window
        self.root_window.title("TeX 文字チェッカー (範囲指定対応)")
        self.root_window.geometry("850x760")

        self.selected_folder = ""
        self.files_to_check = []
        self.all_results_data = []
        self.last_searched_char = "，"
        
        # Configuration for search modes (text and value)
        self.search_modes_config = [
            ("数式環境内のみ", "math_only"),
            ("数式環境外のみ", "text_only_strict"),
            ("ドキュメント全体(コメント除く)", "document_wide"),
        ]
        self.last_search_mode = self.search_modes_config[0][1] # Default to the first mode's value

        # Configuration for filter options
        self.filter_var_options = {
            "all": "すべて表示", "issues_only": "問題ありのみ",
            "no_issues": "問題なしのみ", "errors_only": "エラーありのみ"
        }

        # --- UI Elements ---
        top_frame = ttk.Frame(root_window, padding="10")
        top_frame.pack(fill=tk.X)

        folder_select_frame = ttk.LabelFrame(top_frame, text="検査対象フォルダ", padding="5")
        folder_select_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.select_folder_button = ttk.Button(folder_select_frame, text="フォルダを選択", command=self.select_folder_dialog)
        self.select_folder_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.selected_folder_label = ttk.Label(folder_select_frame, text="選択フォルダ: なし")
        self.selected_folder_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.num_files_label = ttk.Label(folder_select_frame, text="TeXファイル数: 0")
        self.num_files_label.pack(side=tk.LEFT, padx=5)

        options_run_frame = ttk.LabelFrame(top_frame, text="オプションと実行", padding="5")
        options_run_frame.pack(side=tk.LEFT, padx=5, fill=tk.Y)

        ttk.Label(options_run_frame, text="検査文字:").grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.target_char_var = tk.StringVar(value="，")
        self.target_char_entry = ttk.Entry(options_run_frame, textvariable=self.target_char_var, width=10)
        self.target_char_entry.grid(row=0, column=1, padx=5, pady=2, sticky=tk.EW)

        ttk.Label(options_run_frame, text="検査範囲:").grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        self.search_mode_var = tk.StringVar(value=self.last_search_mode) 
        self.search_mode_radios = []
        for i, (text, val) in enumerate(self.search_modes_config):
            rb = ttk.Radiobutton(options_run_frame, text=text, variable=self.search_mode_var, value=val)
            rb.grid(row=2+i, column=0, columnspan=2, padx=5, pady=1, sticky=tk.W)
            self.search_mode_radios.append(rb)

        self.ignore_text_var = tk.BooleanVar()
        self.ignore_text_check = ttk.Checkbutton(
            options_run_frame, text="\\text{}等無視(実験的, 数式内のみ)", variable=self.ignore_text_var
        )
        self.ignore_text_check.grid(row=2+len(self.search_modes_config), column=0, columnspan=2, padx=5, pady=2, sticky=tk.W)

        self.run_button = ttk.Button(options_run_frame, text="検査実行", command=self.run_check)
        self.run_button.grid(row=3+len(self.search_modes_config), column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        
        filter_frame = ttk.LabelFrame(root_window, text="結果フィルタ", padding="10")
        filter_frame.pack(fill=tk.X, padx=10, pady=5)
        self.filter_var = tk.StringVar(value="all")
        
        filters_display_config = [ # Order for display
            ("all", self.filter_var_options["all"]), 
            ("issues_only", self.filter_var_options["issues_only"]),
            ("no_issues", self.filter_var_options["no_issues"]), 
            ("errors_only", self.filter_var_options["errors_only"]),
        ]
        for val, text in filters_display_config: # Iterate using value then text
            rb = ttk.Radiobutton(filter_frame, text=text, variable=self.filter_var, value=val, command=self.apply_filter_and_display)
            rb.pack(side=tk.LEFT, padx=10)
        self.clear_button = ttk.Button(filter_frame, text="結果クリア", command=self.clear_all_data_and_display)
        self.clear_button.pack(side=tk.RIGHT, padx=5)

        results_display_frame = ttk.Frame(root_window, padding="10")
        results_display_frame.pack(fill=tk.BOTH, expand=True)
        self.results_text = scrolledtext.ScrolledText(results_display_frame, wrap=tk.WORD, height=20, width=90)
        self.results_text.pack(fill=tk.BOTH, expand=True)
        self.results_text.configure(state='disabled')

        self.summary_label = ttk.Label(root_window, text="サマリー: まだ検査していません", padding="5")
        self.summary_label.pack(fill=tk.X, padx=10, pady=5)

        style = ttk.Style()
        try: style.theme_use('clam')
        except tk.TclError: print("Clam theme not available, using default.")

    def select_folder_dialog(self):
        folderpath = filedialog.askdirectory(title="検査対象のルートフォルダを選択")
        if folderpath:
            self.selected_folder = folderpath
            self.selected_folder_label.config(text=f"選択フォルダ: {os.path.basename(self.selected_folder)}")
            self.find_tex_files_in_folder()
            self.clear_all_data_and_display()
        else:
            if not self.selected_folder:
                self.selected_folder_label.config(text="選択フォルダ: なし")
                self.num_files_label.config(text="TeXファイル数: 0")

    def find_tex_files_in_folder(self):
        self.files_to_check = []
        if not self.selected_folder: return
        for dirpath, _, filenames in os.walk(self.selected_folder):
            for filename in filenames:
                if filename.lower().endswith(".tex"):
                    self.files_to_check.append(os.path.join(dirpath, filename))
        self.num_files_label.config(text=f"TeXファイル数: {len(self.files_to_check)}")
        if not self.files_to_check and self.selected_folder:
             messagebox.showinfo("ファイルなし", f"{self.selected_folder} 以下に .tex ファイルが見つかりませんでした。", parent=self.root_window)

    def clear_all_data_and_display(self):
        self.all_results_data = []
        self.results_text.configure(state='normal')
        self.results_text.delete(1.0, tk.END)
        self.results_text.configure(state='disabled')
        self.summary_label.config(text="サマリー: 結果がクリアされました。")
        self.last_searched_char = self.target_char_var.get()
        self.last_search_mode = self.search_mode_var.get()

    def run_check(self):
        if not self.selected_folder:
            messagebox.showwarning("フォルダ未選択", "検査対象のフォルダを選択してください。", parent=self.root_window)
            return
        if not self.files_to_check:
            messagebox.showwarning("ファイルなし", f"{self.selected_folder} 以下にチェック対象の .tex ファイルがありません。", parent=self.root_window)
            return

        target_char_to_check = self.target_char_var.get()
        if not target_char_to_check:
            messagebox.showwarning("検査文字未入力", "検査する文字を入力してください。", parent=self.root_window)
            return
        
        current_search_mode = self.search_mode_var.get()
        self.last_searched_char = target_char_to_check
        self.last_search_mode = current_search_mode

        self.all_results_data = []
        ignore_text_flag = self.ignore_text_var.get()
        
        progress_window = tk.Toplevel(self.root_window)
        progress_window.title("検査中...")
        progress_window.geometry("350x80")
        progress_window.transient(self.root_window)
        progress_window.grab_set()
        
        search_mode_display_text = current_search_mode 
        for text, val in self.search_modes_config:
            if val == current_search_mode:
                search_mode_display_text = text
                break
        
        ttk.Label(progress_window, text=f"検査文字 '{target_char_to_check}' (範囲: {search_mode_display_text}) で検査中...").pack(pady=10)
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(progress_window, variable=progress_var, maximum=len(self.files_to_check), length=330)
        progress_bar.pack(pady=5)
        self.root_window.update_idletasks()

        for i, filepath in enumerate(self.files_to_check):
            result_dict = find_target_char_in_tex(filepath, target_char_to_check, ignore_text_flag, current_search_mode)
            self.all_results_data.append((filepath, result_dict))
            
            progress_var.set(i + 1)
            if i % 5 == 0 or i == len(self.files_to_check) - 1:
                progress_window.update_idletasks()
        
        progress_window.destroy()
        self.apply_filter_and_display()

    def apply_filter_and_display(self):
        if not self.all_results_data and self.files_to_check:
            self.summary_label.config(text="サマリー: まず「検査実行」をしてください。")
            self.results_text.configure(state='normal')
            self.results_text.delete(1.0, tk.END)
            self.results_text.insert(tk.END, "検査結果がありません。「検査実行」ボタンを押してください。")
            self.results_text.configure(state='disabled')
            return
        if not self.all_results_data:
            self.summary_label.config(text="サマリー: フォルダを選択し、検査を実行してください。")
            return

        self.results_text.configure(state='normal')
        self.results_text.delete(1.0, tk.END)

        current_filter = self.filter_var.get()
        output_count = 0
        total_processed = len(self.all_results_data)
        files_with_issues_summary = 0
        total_individual_issues_summary = 0
        files_with_errors_summary = 0
        
        searched_char_for_display = self.last_searched_char
        search_mode_for_display_val = self.last_search_mode
        
        search_mode_display_text = search_mode_for_display_val
        for text, val in self.search_modes_config:
            if val == search_mode_for_display_val:
                search_mode_display_text = text
                break

        self.results_text.insert(tk.END, f"--- 検査文字 '{searched_char_for_display}' (範囲: {search_mode_display_text}) の結果 ---\n\n")

        for filepath, result_data in self.all_results_data:
            relative_filepath = os.path.relpath(filepath, self.selected_folder)
            error_msg = result_data.get("error_message")
            issues_list = result_data.get("issues_list", [])

            has_error = bool(error_msg)
            has_issues = bool(issues_list)

            if has_error: files_with_errors_summary += 1
            if has_issues: 
                files_with_issues_summary +=1
                total_individual_issues_summary += len(issues_list)

            display_this_file = False
            if current_filter == "all": display_this_file = True
            elif current_filter == "issues_only" and has_issues and not has_error: display_this_file = True
            elif current_filter == "no_issues" and not has_issues and not has_error: display_this_file = True
            elif current_filter == "errors_only" and has_error: display_this_file = True
            
            if display_this_file:
                output_count += 1
                if has_error:
                    self.results_text.insert(tk.END, f"--- ERROR checking {relative_filepath} ---\n")
                    self.results_text.insert(tk.END, f"  {error_msg}\n")
                elif has_issues:
                    issue_type_display = issues_list[0].get('type', 'Unknown type') if issues_list else 'Issues'
                    self.results_text.insert(tk.END, f"--- ISSUES ('{searched_char_for_display}') in '{issue_type_display}' in {relative_filepath} ---\n")
                    for issue in issues_list:
                        detected_char_display = issue.get('detected_char', searched_char_for_display)
                        self.results_text.insert(tk.END, 
                            f"{os.path.relpath(issue['file'], self.selected_folder)}:{issue['line']}:{issue['col']}: "
                            f"'{detected_char_display}' in '{issue['type']}'.\n"
                        )
                        self.results_text.insert(tk.END, f"  L{issue['line']}: {issue['context']}\n")
                        
                        col_in_context = issue['col'] - 1
                        snippet_window = 15
                        detected_len = len(issue.get('detected_char', ''))
                        
                        # Find actual start of detected_char in context for robust highlighting
                        highlight_start_in_context = -1
                        # Try to find around the expected column, case-insensitively if needed
                        search_start_highlight = max(0, col_in_context - snippet_window//2) # Search a bit before
                        search_end_highlight = min(len(issue['context']), col_in_context + detected_len + snippet_window//2) # Search a bit after
                        try:
                            highlight_start_in_context = issue['context'].lower().index(detected_char_display.lower(), search_start_highlight, search_end_highlight)
                        except ValueError:
                             # If not found in the vicinity, fall back to col_in_context if it's plausible
                            if 0 <= col_in_context < len(issue['context']) and \
                               issue['context'][col_in_context : col_in_context + detected_len].lower() == detected_char_display.lower():
                                highlight_start_in_context = col_in_context
                            else: # Still not found, can't highlight accurately
                                 pass # Will skip highlight or use a generic message

                        if highlight_start_in_context != -1:
                            actual_highlighted_segment = issue['context'][highlight_start_in_context : highlight_start_in_context + detected_len]
                            snippet_display_start = max(0, highlight_start_in_context - snippet_window)
                            snippet_display_end = min(len(issue['context']), highlight_start_in_context + detected_len + snippet_window)
                            prefix_snippet = "..." if snippet_display_start > 0 else ""
                            suffix_snippet = "..." if snippet_display_end < len(issue['context']) else ""
                            self.results_text.insert(tk.END, 
                                f"  Near: {prefix_snippet}"
                                f"{issue['context'][snippet_display_start : highlight_start_in_context]}"
                                f">>>{actual_highlighted_segment}<<<"
                                f"{issue['context'][highlight_start_in_context + detected_len : snippet_display_end]}"
                                f"{suffix_snippet}\n"
                            )
                        else:
                            self.results_text.insert(tk.END, f"  (Could not accurately highlight '{detected_char_display}' in context: {issue['context']})\n")

                        self.results_text.insert(tk.END, "-" * 10 + "\n")
                    self.results_text.insert(tk.END, f"Found {len(issues_list)} instance(s) of '{searched_char_for_display}' in this file ({issue_type_display}).\n")
                else:
                    self.results_text.insert(tk.END, f"--- No instances of '{searched_char_for_display}' found in {relative_filepath} (Mode: {search_mode_display_text}) ---\n")
                self.results_text.insert(tk.END, "---" + "-" * (len(relative_filepath) + 20) + "---\n\n")

        if output_count == 0 and self.all_results_data:
            self.results_text.insert(tk.END, f"選択されたフィルタ '{self.filter_var_options.get(current_filter, current_filter)}' に一致するファイルはありませんでした (検査文字: '{searched_char_for_display}', 範囲: {search_mode_display_text})。\n")

        self.results_text.configure(state='disabled')
        self.results_text.see(tk.END)
        
        summary_text = (f"サマリー (文字:'{searched_char_for_display}', 範囲:{search_mode_display_text}): {total_processed}ファイル検査完了。 "
                        f"問題あり: {files_with_issues_summary}ファイル ({total_individual_issues_summary}件)。 "
                        f"エラー: {files_with_errors_summary}ファイル。 "
                        f"(現在 {output_count}ファイル表示中)")
        self.summary_label.config(text=summary_text)

if __name__ == "__main__":
    root = tk.Tk()
    app = TexCharCheckerApp(root)
    root.mainloop()