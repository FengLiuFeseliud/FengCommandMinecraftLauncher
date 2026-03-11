from rich.prompt import Prompt


name = Prompt.ask("回车显示下一页, 输入 exit 退出", choices=["Paul", "Jessica", "Duncan"], default="Paul")