#!/usr/bin/env python3
"""go2_watch.py — tegrastats 解析监控面板（GO2 语义导航 bringup 专用）

在容器里运行（tegrastats 已 docker cp 进去的前提下）：
    python3 go2_watch.py                    # 直播 + 报警
    python3 go2_watch.py --log run1.csv     # 直播 + 落盘（CSV，首列 epoch 秒，可对 ROS 日志）

报警阈值与 bringup 验收线一致：
    tj >= 85C 警告(WARN)，>= 90C 严重(CRIT)   -- 热预算（throttle ~97C）
    全 8 核 >=85% 持续 >=4 个采样 (~2s)        -- CPU 饱和 burst（饿死感知/relay/hazard 的前兆）
    任一核频率 <1500 MHz                     -- 功率/电压节流（电机电流导致电压下垂的信号）
    lfb < 100 x 4MB                         -- 大页内存耗尽（昨天 lfb=14 时系统开始抖动）
    GR3D >=95% 持续 >=10 个采样 (~5s)         -- GPU 钉死（检测链无余量）
    SWAP > 0                                 -- 开始换页（实时性崩坏前兆）

行首 epoch 秒与 ROS 日志时间戳同源（无 sim_time 时），事后可直接对齐
"发 goal 的时刻 ↔ CPU burst ↔ 场景图冻结"。
"""

import argparse
import re
import subprocess
import sys
import time
from datetime import datetime

RAM_RE = re.compile(r"RAM (\d+)/(\d+)MB \(lfb (\d+)x4MB\)")
SWAP_RE = re.compile(r"SWAP (\d+)/(\d+)MB")
CPU_RE = re.compile(r"CPU \[(.*?)\]")
CORE_RE = re.compile(r"(\d+)%@(\d+)")
GR3D_RE = re.compile(r"GR3D_FREQ (\d+)%")
TJ_RE = re.compile(r"tj@([\d.]+)C")


def parse_line(line):
    d = {"raw": line.rstrip()}
    m = RAM_RE.search(line)
    if m:
        d["ram_mb"], d["ram_total_mb"], d["lfb"] = int(m[1]), int(m[2]), int(m[3])
    m = SWAP_RE.search(line)
    if m:
        d["swap_mb"] = int(m[1])
    m = CPU_RE.search(line)
    if m:
        cores = CORE_RE.findall(m.group(1))
        d["cpu_pct"] = [int(c[0]) for c in cores]
        d["cpu_mhz"] = [int(c[1]) for c in cores]
    m = GR3D_RE.search(line)
    if m:
        d["gr3d"] = int(m.group(1))
    m = TJ_RE.search(line)
    if m:
        d["tj"] = float(m.group(1))
    return d if "tj" in d else None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", type=int, default=500, help="tegrastats 采样 ms (默认 500)")
    ap.add_argument("--log", default="", help="CSV 落盘路径（可选）")
    args = ap.parse_args()

    proc = subprocess.Popen(
        ["tegrastats", "--interval", str(args.interval)],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )

    log_f = open(args.log, "a") if args.log else None
    if log_f:
        log_f.write("epoch,tj_c,gr3d_pct,cpu_max,cpu_avg,freq_min_mhz,lfb,swap_mb\n")

    n = 0
    tj_sum = tj_max = 0.0
    gr3d_busy = 0            # GR3D>50% 的采样数（占空比）
    cpu_sat_samples = 0      # 全核>=85% 的采样数
    streak_sat = 0           # 连续全核>=85% 计数
    streak_gpu = 0           # 连续 GR3D>=95% 计数
    min_freq = 10**9

    print(f"[go2_watch] 开始监控 interval={args.interval}ms  log={args.log or '-'}  (Ctrl-C 结束并出总结)")
    try:
        for line in proc.stdout:
            d = parse_line(line)
            if d is None:
                continue
            n += 1
            now = time.time()
            alarms = []

            tj = d["tj"]; tj_sum += tj; tj_max = max(tj_max, tj)
            if tj >= 90:   alarms.append("CRIT_TJ")
            elif tj >= 85: alarms.append("WARN_TJ")

            gr3d = d.get("gr3d", 0)
            if gr3d > 50: gr3d_busy += 1
            if gr3d >= 95:
                streak_gpu += 1
                if streak_gpu >= 10: alarms.append("GPU_PINNED")
            else:
                streak_gpu = 0

            cpu = d.get("cpu_pct", [0]); mhz = d.get("cpu_mhz", [0])
            cpu_max = max(cpu); cpu_avg = sum(cpu) / len(cpu)
            f_min = min(mhz); min_freq = min(min_freq, f_min)
            if f_min < 1500: alarms.append("FREQ_DROP")
            if len(cpu) >= 4 and all(c >= 85 for c in cpu):
                streak_sat += 1; cpu_sat_samples += 1
                if streak_sat >= 4: alarms.append("CPU_SAT")
            else:
                streak_sat = 0

            if d.get("lfb", 999) < 100: alarms.append("LOW_LFB")
            if d.get("swap_mb", 0) > 0: alarms.append("SWAP")

            flag = ("  <<< " + ",".join(alarms)) if alarms else ""
            print(f"[{now:.0f}] tj={tj:5.1f}C  GR3D={gr3d:3d}%  "
                  f"CPU[max={cpu_max:3d} avg={cpu_avg:4.1f} fmin={f_min}]  "
                  f"lfb={d.get('lfb', -1):5d}  swap={d.get('swap_mb', 0):4d}{flag}",
                  flush=True)

            if log_f:
                log_f.write(f"{now:.0f},{tj},{gr3d},{cpu_max},{cpu_avg:.1f},{f_min},"
                            f"{d.get('lfb', -1)},{d.get('swap_mb', 0)}\n")
                log_f.flush()
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        if log_f:
            log_f.close()
        if n:
            print("\n===== 总结 =====")
            print(f"采样数 {n}  ({n * args.interval / 1000:.0f}s)")
            print(f"tj: avg={tj_sum/n:.1f}C  max={tj_max:.1f}C")
            print(f"GPU 占空比(GR3D>50%): {gr3d_busy/n*100:.0f}%")
            print(f"CPU 饱和采样(全核>=85%): {cpu_sat_samples}  ({cpu_sat_samples/n*100:.0f}%)")
            print(f"最低核频: {min_freq if min_freq < 10**9 else '-'} MHz")


if __name__ == "__main__":
    main()
