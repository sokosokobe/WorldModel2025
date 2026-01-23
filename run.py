"""Script to run end-to-end evaluation on the benchmark.

Modified from https://github.com/web-arena-x/webarena/blob/main/run.py.
"""
import argparse
import glob
import json
import logging
import os
import random
import subprocess
import tempfile
import time
import sys
from pathlib import Path
from typing import Optional, Dict, List, Any
import platform

import openai
import requests
import torch
from PIL import Image
import re

from agent import (
    PromptAgent,
    construct_agent,
)
from agent.prompts import *
from browser_env import (
    Action,
    ActionTypes,
    ScriptBrowserEnv,
    StateInfo,
    Trajectory,
    create_stop_action,
)
from browser_env.actions import is_equivalent
from browser_env.auto_login import get_site_comb_from_filepath
from browser_env.helper_functions import (
    RenderHelper,
    get_action_description,
)
from evaluation_harness import evaluator_router, image_utils

print("=== RUNTIME INFO ===")
print("sys.executable:", sys.executable)
print("cwd:", os.getcwd())
print("platform:", platform.platform())
print("WSL:", "microsoft" in platform.release().lower())
print("HOSTNAME:", os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME"))
print("====================")

DATASET = os.environ["DATASET"]

LOG_FOLDER = "log_files"
Path(LOG_FOLDER).mkdir(parents=True, exist_ok=True)
LOG_FILE_NAME = f"{LOG_FOLDER}/log_{time.strftime('%Y%m%d%H%M%S', time.localtime())}_{random.randint(0, 10000)}.log"


from typing import Optional, Dict, List, Any

# =========================
# Cart count / add-to-cart detection
# =========================

# Magento/Luma系の「カートアイコンの個数」候補セレクタ
_CART_COUNT_SELECTORS = [
    ".minicart-wrapper .action.showcart .counter.qty .counter-number",
    ".minicart-wrapper .action.showcart .counter-number",
    ".minicart-wrapper .action.showcart .counter.qty",
    "a.action.showcart .counter-number",
    "a.action.showcart .counter.qty",
    "a[href*='checkout/cart'] .counter-number",
    "a[href*='checkout/cart'] .counter.qty",
]


_SUCCESS_MSG_SELECTORS = [
    "div.message-success",
    "div.messages div.message-success",
    "div.page.messages div.message-success",
]

_ERROR_MSG_SELECTORS = [
    "div.message-error",
    "div.messages div.message-error",
    "div.page.messages div.message-error",
]

def _extract_int(s: str) -> Optional[int]:
    if not s:
        return None
    m = re.search(r"\d+", s.replace(",", ""))
    return int(m.group(0)) if m else None

def _first_text_by_selectors(page, selectors, timeout_ms: int = 200) -> Optional[str]:
    """Return first non-empty innerText among selectors, else None."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                continue
            t = loc.inner_text(timeout=timeout_ms).strip()
            if t:
                return t
        except Exception:
            continue
    return None


def get_cart_count(page) -> int:
    """
    Read cart item count from the minicart counter.
    IMPORTANT: ページ全体の数字を拾わない（50x60 等に引っ張られるため）
    """
    for sel in _CART_COUNT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                continue
            t = loc.inner_text(timeout=200).strip()
            v = _extract_int(t)
            if v is not None:
                return v
        except Exception:
            continue

    # 最終手段: "My Cart 3 items" みたいにリンクテキストに数字が混ざる場合
    try:
        txt = page.locator("a:has-text('My Cart')").first.inner_text(timeout=200)
        v = _extract_int(txt)
        return v if v is not None else 0
    except Exception:
        return 0


def detect_add_to_cart(page, before_count: int) -> tuple[str, int, str, Dict[str, Any]]:
    """
    Returns:
      status: 'added' | 'error' | 'no_change'
      after_count
      feedback_str
      event_dict (meta_data に入れる用)
    """
    after_count = get_cart_count(page)

    success_msg = _first_text_by_selectors(page, _SUCCESS_MSG_SELECTORS)
    error_msg = _first_text_by_selectors(page, _ERROR_MSG_SELECTORS)

    if error_msg:
        status = "error"
        feedback = f"[Cart] Add failed: {error_msg}"
    elif success_msg:
        status = "added"
        feedback = f"[Cart] Added (msg): {success_msg}"
    elif after_count > before_count:
        status = "added"
        feedback = f"[Cart] Added: count {before_count} -> {after_count}"
    else:
        status = "no_change"
        feedback = "[Cart] No change"

    evt = {
        "status": status,
        "before": before_count,
        "after": after_count,
        "success_msg": success_msg or "",
        "error_msg": error_msg or "",
        "url": getattr(page, "url", ""),
    }
    return status, after_count, feedback, evt


logger = logging.getLogger("logger")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
logger.addHandler(console_handler)

file_handler = logging.FileHandler(LOG_FILE_NAME)
file_handler.setLevel(logging.DEBUG)
logger.addHandler(file_handler)

# Set the log format
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# ==========================
# Shopping cart detection helpers
# ==========================

_CART_ERROR_SUBSTRINGS = [
    "required option",  # "The product's required option(s) weren't entered"
    "weren't entered",
    "wasn't entered",
    "please specify",
    "this is a required field",
    "out of stock",
]


def _extract_ints(text: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", text or "")]


def get_cart_count(page) -> int:
    """
    Returns the cart item count shown in the header (best-effort).
    If not found, returns 0.
    """
    selectors = [
        'a:has-text("My Cart")',
        "a.action.showcart",
        "div.minicart-wrapper a.action.showcart",
        "#minicart-wrapper a.action.showcart",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() <= 0:
                continue
            txt = loc.first.inner_text(timeout=500) or ""
            nums = _extract_ints(txt)
            if nums:
                # "My Cart 12 12 items" みたいに重複するので max を取る
                return max(nums)
        except Exception:
            pass

    # 予備：よくあるカウンタ
    for sel in ["span.counter-number", "span.counter.qty", "span.count"]:
        try:
            loc = page.locator(sel)
            if loc.count() <= 0:
                continue
            txt = loc.first.inner_text(timeout=300) or ""
            nums = _extract_ints(txt)
            if nums:
                return max(nums)
        except Exception:
            pass

    return 0


def _get_cart_message_text(page) -> str | None:
    """
    Magento系のメッセージ領域から、表示中メッセージを拾う（best-effort）
    """
    msg_selectors = [
        ".message-success",
        ".message-error",
        ".messages .message",
        ".page.messages",
        "div.messages",
    ]
    for sel in msg_selectors:
        try:
            loc = page.locator(sel)
            if loc.count() <= 0:
                continue
            # 目視的に出てるやつだけ拾う
            t = loc.first.inner_text(timeout=300)
            t = (t or "").strip()
            if t:
                return t
        except Exception:
            pass
    return None


def detect_add_to_cart(page, cart_before: int):
    """
    Returns (status, cart_after, feedback)
      status: "success" | "fail" | "info" | "none"
    """
    try:
        page.wait_for_timeout(200)  # 反映待ち（軽く）
    except Exception:
        pass

    cart_after = get_cart_count(page)
    msg = _get_cart_message_text(page)

    status = "none"
    if cart_after > cart_before:
        status = "success"
    elif msg:
        low = msg.lower()
        if any(s in low for s in _CART_ERROR_SUBSTRINGS):
            status = "fail"
        elif ("added" in low and "cart" in low) or ("shopping cart" in low and "added" in low):
            status = "success"
        else:
            status = "info"

    if status == "none":
        return "none", cart_after, ""

    short_msg = msg.replace("\n", " ").strip() if msg else ""
    feedback = f"[Cart] Add {status.upper()}: count {cart_before}->{cart_after}"
    if short_msg:
        feedback += f" | {short_msg}"
    return status, cart_after, feedback


def config() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run end-to-end evaluation on the benchmark"
    )
    parser.add_argument(
        "--render", action="store_true", help="Render the browser"
    )

    parser.add_argument(
        "--slow_mo",
        type=int,
        default=0,
        help="Slow down the browser by the specified amount",
    )
    parser.add_argument(
        "--action_set_tag", default="id_accessibility_tree", help="Action type"
    )
    parser.add_argument(
        "--observation_type",
        choices=[
            "accessibility_tree",
            "accessibility_tree_with_captioner",
            "html",
            "image",
            "image_som",
        ],
        default="accessibility_tree",
        help="Observation type",
    )
    parser.add_argument(
        "--current_viewport_only",
        action="store_true",
        help="Only use the current viewport for the observation",
    )
    parser.add_argument("--viewport_width", type=int, default=1280)
    parser.add_argument("--viewport_height", type=int, default=2048)
    parser.add_argument("--save_trace_enabled", action="store_true")
    parser.add_argument("--sleep_after_execution", type=float, default=0.0)

    parser.add_argument("--max_steps", type=int, default=30)

    # agent config
    parser.add_argument("--agent_type", type=str, default="prompt")
    parser.add_argument(
        "--instruction_path",
        type=str,
        default="agents/prompts/state_action_agent.json",
    )
    parser.add_argument(
        "--parsing_failure_th",
        help="When consecutive parsing failures exceed this threshold, the agent will terminate early.",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--repeating_action_failure_th",
        help="When consecutive repeated actions exceed this threshold, the agent will terminate early.",
        type=int,
        default=5,
    )

    parser.add_argument("--test_config_base_dir", type=str)

    parser.add_argument(
        "--eval_captioning_model_device",
        type=str,
        default="cpu",
        choices=["cpu", "cuda"],
        help="Device to run eval captioning model on. By default, runs it on CPU.",
    )
    parser.add_argument(
        "--eval_captioning_model",
        type=str,
        default="Salesforce/blip2-flan-t5-xl",
        choices=["Salesforce/blip2-flan-t5-xl"],
        help="Captioning backbone for VQA-type evals.",
    )
    parser.add_argument(
        "--captioning_model",
        type=str,
        default="Salesforce/blip2-flan-t5-xl",
        choices=["Salesforce/blip2-flan-t5-xl", "llava-hf/llava-1.5-7b-hf"],
        help="Captioning backbone for accessibility tree alt text.",
    )

    # lm config
    parser.add_argument("--provider", type=str, default="openai")
    parser.add_argument("--model", type=str, default="gpt-3.5-turbo-0613")
    parser.add_argument("--mode", type=str, default="chat")
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top_p", type=float, default=0.9)
    parser.add_argument("--context_length", type=int, default=0)
    parser.add_argument("--max_tokens", type=int, default=384)
    parser.add_argument("--stop_token", type=str, default=None)
    parser.add_argument(
        "--max_retry",
        type=int,
        help="max retry times to perform generations when parsing fails",
        default=1,
    )
    parser.add_argument(
        "--max_obs_length",
        type=int,
        help="when not zero, will truncate the observation to this length before feeding to the model",
        default=3840,
    )

    # example config
    parser.add_argument("--test_start_idx", type=int, default=0)
    parser.add_argument("--test_end_idx", type=int, default=910)

    # logging related
    parser.add_argument("--result_dir", type=str, default="")
    args = parser.parse_args()

    # check the whether the action space is compatible with the observation space
    if (
        args.action_set_tag == "id_accessibility_tree"
        and args.observation_type
        not in [
            "accessibility_tree",
            "accessibility_tree_with_captioner",
            "image_som",
        ]
    ):
        raise ValueError(
            f"Action type {args.action_set_tag} is incompatible with the observation type {args.observation_type}"
        )

    return args


def early_stop(
    trajectory: Trajectory, max_steps: int, thresholds: dict[str, int]
) -> tuple[bool, str]:
    """Check whether need to stop early"""

    # reach the max step
    num_steps = (len(trajectory) - 1) / 2
    if num_steps >= max_steps:
        return True, f"Reach max steps {max_steps}"

    last_k_actions: list[Action]
    action_seq: list[Action]

    # Case: parsing failure for k times
    k = thresholds["parsing_failure"]
    last_k_actions = trajectory[1::2][-k:]  # type: ignore[assignment]
    if len(last_k_actions) >= k:
        if all(
            [
                action["action_type"] == ActionTypes.NONE
                for action in last_k_actions
            ]
        ):
            return True, f"Failed to parse actions for {k} times"

    # Case: same action for k times
    k = thresholds["repeating_action"]
    last_k_actions = trajectory[1::2][-k:]  # type: ignore[assignment]
    action_seq = trajectory[1::2]  # type: ignore[assignment]

    if len(action_seq) == 0:
        return False, ""

    last_action: Action = action_seq[-1]

    if last_action["action_type"] != ActionTypes.TYPE:
        if len(last_k_actions) >= k:
            if all(
                [
                    is_equivalent(action, last_action)
                    for action in last_k_actions
                ]
            ):
                return True, f"Same action for {k} times"

    else:
        # check the action sequence
        if (
            sum([is_equivalent(action, last_action) for action in action_seq])
            >= k
        ):
            return True, f"Same typing action for {k} times"

    return False, ""


def _page_eval(page, js: str):
    """Playwright page.evaluate() を sync/async 両対応で呼ぶ"""
    try:
        out = page.evaluate(js)
        # asyncの場合だけawait
        if hasattr(out, "__await__"):
            import asyncio
            return asyncio.get_event_loop().run_until_complete(out)
        return out
    except Exception:
        return None


def get_cart_count(page):
    """
    ヘッダの "My Cart 12 items" みたいな表示 or minicartカウンタから個数を取る。
    取れないときは None。
    """
    js = r"""
    () => {
      const tryParse = (s) => {
        if (!s) return null;
        const m = String(s).replace(/[, \t\r\n]/g, '').match(/(\d+)/);
        return m ? parseInt(m[1], 10) : null;
      };

      const selectors = [
        '.minicart-wrapper .counter-number',
        '.minicart-wrapper .counter.qty',
        'a.showcart .counter-number',
        'a.showcart .counter.qty',
        'a[href*="checkout/cart"] .counter-number',
        'a[href*="checkout/cart"] .counter.qty',
      ];

      for (const sel of selectors) {
        const el = document.querySelector(sel);
        const n = tryParse(el && (el.textContent || el.innerText));
        if (n !== null && !Number.isNaN(n)) return n;
      }

      // fallback: "My Cart" を含む要素テキストから数字を拾う
      const els = Array.from(document.querySelectorAll('a, span, div'));
      for (const el of els) {
        const t = (el.innerText || el.textContent || '').trim();
        if (!t) continue;
        if (/\bMy\s*Cart\b/i.test(t)) {
          const n = tryParse(t);
          if (n !== null && !Number.isNaN(n)) return n;
        }
      }
      return null;
    }
    """
    return _page_eval(page, js)


def get_cart_messages(page):
    """
    Magento系のフラッシュメッセージを拾う（成功/失敗/notice）。
    """
    js = r"""
    () => {
      const grab = (sel) => Array.from(document.querySelectorAll(sel))
        .map(e => (e.innerText || e.textContent || '').trim())
        .filter(Boolean);

      const success = grab('.message-success, .messages .message-success, .messages .success');
      const error   = grab('.message-error, .messages .message-error, .messages .error');
      const notice  = grab('.message-notice, .messages .message-notice, .messages .notice');

      return {
        success: success.slice(0, 2),
        error: error.slice(0, 2),
        notice: notice.slice(0, 2),
      };
    }
    """
    out = _page_eval(page, js)
    if isinstance(out, dict):
        return out
    return {"success": [], "error": [], "notice": []}


def detect_add_to_cart(page, before_count):
    """
    before_count と比較してカート増加/失敗を判定。
    戻り値: (status, after_count, feedback_str)
      status: "added" | "failed" | "nochange"
    """
    after_count = get_cart_count(page)
    msgs = get_cart_messages(page)

    # 失敗メッセージ優先
    if msgs.get("error"):
        return "failed", after_count, f"[Cart] Add failed: {msgs['error'][0]}"

    # 個数が増えてたら成功
    if before_count is not None and after_count is not None and after_count > before_count:
        return "added", after_count, f"[Cart] Added: count {before_count} -> {after_count}"

    # 成功メッセージだけ出てる場合（count取れない/変化なしでも）
    if msgs.get("success"):
        return "added", after_count, f"[Cart] Added (msg): {msgs['success'][0]}"

    return "nochange", after_count, "[Cart] No change"

def test(
    args: argparse.Namespace,
    config_file_list: list[str]
) -> None:
    scores = []
    max_steps = args.max_steps

    early_stop_thresholds = {
        "parsing_failure": args.parsing_failure_th,
        "repeating_action": args.repeating_action_failure_th,
    }

    caption_image_fn = None

    if args.observation_type == "accessibility_tree_with_captioner":
        device = torch.device("cuda") if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        caption_image_fn = image_utils.get_captioning_fn(
            device, dtype, args.captioning_model
        )
    else:
        caption_image_fn = None

    # Load a (possibly different) captioning model for running VQA evals.
    if DATASET == 'visualwebarena':
        if (
            caption_image_fn
            and args.eval_captioning_model == args.captioning_model
        ):
            eval_caption_image_fn = caption_image_fn
        else:
            eval_caption_image_fn = image_utils.get_captioning_fn(
                args.eval_captioning_model_device,
                torch.float16
                if (
                    torch.cuda.is_available()
                    and args.eval_captioning_model_device == "cuda"
                )
                else torch.float32,
                args.eval_captioning_model,
            )
    else:
        caption_image_fn = None
        eval_caption_image_fn = None

    agent = construct_agent(
        args,
        captioning_fn=caption_image_fn
        if args.observation_type == "accessibility_tree_with_captioner"
        else None,
    )  # NOTE: captioning_fn here is used for captioning input images.

    env = ScriptBrowserEnv(
        headless=not args.render,
        slow_mo=args.slow_mo,
        observation_type=args.observation_type,
        current_viewport_only=args.current_viewport_only,
        viewport_size={
            "width": args.viewport_width,
            "height": args.viewport_height,
        },
        save_trace_enabled=args.save_trace_enabled,
        sleep_after_execution=args.sleep_after_execution,
        # NOTE: captioning_fn here is used for LLM + captioning baselines.
        # This can be different from the captioning model used for evals.
        captioning_fn=caption_image_fn,
    )

    for config_file in config_file_list:
        try:
            render_helper = RenderHelper(
                config_file, args.result_dir, args.action_set_tag
            )

            # Load task.
            with open(config_file) as f:
                _c = json.load(f)
                intent = _c["intent"]
                task_id = _c["task_id"]
                image_paths = _c.get("image", None)
                images = []

                # automatically login
                if _c["storage_state"]:
                    cookie_file_name = os.path.basename(_c["storage_state"])
                    comb = get_site_comb_from_filepath(cookie_file_name)
                    temp_dir = tempfile.mkdtemp()

                    repo_root = Path(__file__).resolve().parent  # run.py があるディレクトリ

                    # subprocess to renew the cookie
                    subprocess.run(
                        [
                            sys.executable, # ← "python" じゃなくて今使ってるpython
                            "-m", "browser_env.auto_login", # module実行
                            "--auth_folder",
                            temp_dir,
                            "--site_list",
                            *comb,
                        ],
                        check=True,
                        cwd=str(repo_root)
                    )
                    _c["storage_state"] = str(Path(temp_dir) / cookie_file_name)
                    assert os.path.exists(_c["storage_state"])
                    # update the config file
                    config_file = f"{temp_dir}/{os.path.basename(config_file)}"
                    with open(config_file, "w") as f:
                        json.dump(_c, f)

                # Load input images for the task, if any.
                if image_paths is not None:
                    if isinstance(image_paths, str):
                        image_paths = [image_paths]
                    for image_path in image_paths:
                        # Load image either from the web or from a local path.
                        if image_path.startswith("http"):
                            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                            input_image = Image.open(requests.get(image_path, stream=True, headers = headers).raw)
                        else:
                            input_image = Image.open(image_path)

                        images.append(input_image)

            logger.info(f"[Config file]: {config_file}")
            logger.info(f"[Intent]: {intent}")

            agent.reset(config_file)
            trajectory: Trajectory = []
            obs, info = env.reset(options={"config_file": config_file})
            state_info: StateInfo = {"observation": obs, "info": info}
            trajectory.append(state_info)

            meta_data = {"action_history": ["None"]}
            while True:
                early_stop_flag, stop_info = early_stop(
                    trajectory, max_steps, early_stop_thresholds
                )

                if early_stop_flag:
                    action = create_stop_action(f"Early stop: {stop_info}")
                else:
                    try:
                        action = agent.next_action(
                            trajectory,
                            intent,
                            images=images,
                            meta_data=meta_data,
                        )
                    except ValueError as e:
                        # get the error message
                        action = create_stop_action(f"ERROR: {str(e)}")

                trajectory.append(action)

                action_str = get_action_description(
                    action,
                    state_info["info"]["observation_metadata"],
                    action_set_tag=args.action_set_tag,
                    prompt_constructor=agent.prompt_constructor
                    if isinstance(agent, PromptAgent)
                    else None,
                )
                render_helper.render(
                    action, state_info, meta_data, args.render_screenshot
                )
                meta_data["action_history"].append(action_str)

                if action["action_type"] == ActionTypes.STOP:
                    break
                
                # --- Add-to-cart検知: step前のカート数 ---
                cart_before = 0
                try:
                    cart_before = get_cart_count(env.page)
                except Exception:
                    pass

                obs, _, terminated, _, info = env.step(action)
                # --- Add-to-cart検知: step後の判定 ---
                try:
                    cart_status, cart_after, cart_feedback, cart_evt = detect_add_to_cart(env.page, cart_before)

                    # 次の next_action() に渡す（prompt側で見える前提）
                    meta_data["last_cart_event"] = cart_evt

                    # 次の思考で見えるように action_history に追記（重要）
                    try:
                        meta_data["action_history"][-1] = meta_data["action_history"][-1] + " | " + cart_feedback
                    except Exception:
                        pass

                    logger.info(cart_feedback)
                except Exception:
                    pass

                state_info = {"observation": obs, "info": info}
                trajectory.append(state_info)

                if terminated:
                    # add a action place holder
                    trajectory.append(create_stop_action(""))
                    break

            # NOTE: eval_caption_image_fn is used for running eval_vqa functions.
            evaluator = evaluator_router(
                config_file, captioning_fn=eval_caption_image_fn
            )
            score = evaluator(
                trajectory=trajectory,
                config_file=config_file,
                page=env.page
            )

            scores.append(score)

            if score == 1:
                logger.info(f"[Result] (PASS) {config_file}")
            else:
                logger.info(f"[Result] (FAIL) {config_file}")

            if args.save_trace_enabled:
                env.save_trace(
                    Path(args.result_dir) / "traces" / f"{task_id}.zip"
                )
        except openai.OpenAIError as e:
            logger.info(f"[OpenAI Error] {repr(e)}")
        except Exception as e:
            logger.info(f"[Unhandled Error] {repr(e)}]")
            import traceback

            # write to error file
            with open(Path(args.result_dir) / "error.txt", "a") as f:
                f.write(f"[Config file]: {config_file}\n")
                f.write(f"[Unhandled Error] {repr(e)}\n")
                f.write(traceback.format_exc())  # write stack trace to file

        render_helper.close()

    env.close()
    if len(scores):
        logger.info(f"Average score: {sum(scores) / len(scores)}")


def prepare(args: argparse.Namespace) -> None:
    # convert prompt python files to json
    from agent.prompts import to_json

    to_json.run()

    # prepare result dir
    result_dir = args.result_dir
    if not result_dir:
        result_dir = (
            f"cache/results_{time.strftime('%Y%m%d%H%M%S', time.localtime())}"
        )
    if not Path(result_dir).exists():
        Path(result_dir).mkdir(parents=True, exist_ok=True)
        args.result_dir = result_dir
        logger.info(f"Create result dir: {result_dir}")

    if not (Path(result_dir) / "traces").exists():
        (Path(result_dir) / "traces").mkdir(parents=True)

    # log the log file
    with open(os.path.join(result_dir, "log_files.txt"), "a+") as f:
        f.write(f"{LOG_FILE_NAME}\n")


def get_unfinished(config_files: list[str], result_dir: str) -> list[str]:
    result_files = glob.glob(f"{result_dir}/*.html")
    task_ids = [
        os.path.basename(f).split(".")[0].split("_")[1] for f in result_files
    ]
    unfinished_configs = []
    for config_file in config_files:
        task_id = os.path.basename(config_file).split(".")[0]
        if task_id not in task_ids:
            unfinished_configs.append(config_file)
    return unfinished_configs


def dump_config(args: argparse.Namespace) -> None:
    config_file = Path(args.result_dir) / "config.json"
    if not config_file.exists():
        with open(config_file, "w") as f:
            json.dump(vars(args), f, indent=4)
            logger.info(f"Dump config to {config_file}")


if __name__ == "__main__":
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    args = config()
    args.sleep_after_execution = 2.5
    prepare(args)

    test_config_base_dir = args.test_config_base_dir

    test_file_list = []
    st_idx = args.test_start_idx
    ed_idx = args.test_end_idx
    for i in range(st_idx, ed_idx):
        test_file_list.append(os.path.join(test_config_base_dir, f"{i}.json"))
    test_file_list = get_unfinished(test_file_list, args.result_dir)
    print(f"Total {len(test_file_list)} tasks left")
    # args.render = False
    args.render_screenshot = True
    args.save_trace_enabled = True

    args.current_viewport_only = True
    dump_config(args)

    test(args, test_file_list)
