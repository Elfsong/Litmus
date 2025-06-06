# coding: utf-8

# Author: Du Mingzhe (mingzhe@nus.edu.sg)
# Date: 2025-06-06

import time
import json
import utils
import random
import requests
import textwrap
from tqdm import tqdm
from typing import Any
from tabulate import tabulate
from datasets import load_dataset
from multiprocessing.dummy import Pool as ThreadPool

class LitmusTest:
    def __init__(self, lang, number_of_workers, case_multiply, max_test_packs, monolith_timeout) -> None:
        self.lang = lang
        self.case_multiply = case_multiply
        self.max_test_packs = max_test_packs
        self.monolith_timeout = monolith_timeout
        self.number_of_workers = number_of_workers

class VenusLitmusTest(LitmusTest):
    def __init__(self, lang, number_of_workers, case_multiply, max_test_packs, monolith_timeout) -> None:
        super().__init__(lang, number_of_workers, case_multiply, max_test_packs, monolith_timeout)
        self.venus_dataset = load_dataset("Elfsong/Venus", lang, split="train")
        self.leetcode_dataset = load_dataset("Elfsong/leetcode_data", split="train")
        self.leetcode_len = len(self.leetcode_dataset)
        self.venus_dict = {int(instance['question_id']): instance for instance in self.venus_dataset}

    def run_distribution(self):
        for index, instance in enumerate(self.leetcode_dataset):
            problem_id = instance['problem_id']
            print(f"[+] Processing Problem [{problem_id}]...")

            # 1. Instance Check
            if not instance['test_case_runners']: continue
            if not instance['test_case_runners'][self.lang]: continue
            if not instance['test_case_evaluator']: continue
            if not instance['solutions']: continue
            if not instance['solutions'][self.lang]: continue

            # 2. Prepare the solution code
            solution_list = list()

            # 2.1 Canonical Solutions
            for solution in instance['solutions'][self.lang]:
                solution_list.append(solution)

            # 2.2 Human Solutions
            if problem_id in self.venus_dict:
                rt_list = self.venus_dict[problem_id]['rt_list']
                mm_list = self.venus_dict[problem_id]['mm_list']
                for solution in rt_list + mm_list:
                    solution_list.append(solution['code'])
            
            # 3. Solution Deduplication
            solution_list = list(set(solution_list))
            
            # 4. Construct Test Packs
            solution_list = random.sample(solution_list, min(self.max_test_packs, len(solution_list)))
            test_packs = [(self.lang, solution, instance, self.case_multiply, self.monolith_timeout) for solution in solution_list]

            print(f'[+] Problem {problem_id} [{index}/{self.leetcode_len}] - {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')

            # 5. Parallel Evaluation
            execution_results = list()
            with ThreadPool(self.number_of_workers) as pool:
                with tqdm(total=len(test_packs), desc='Solution Evaluation') as pbar:
                    for result in pool.imap(lambda args: utils.run_evaluation(*args), test_packs):
                        execution_results.append(result)
                        pbar.update(1)

            # Prepare the table header
            headers = ["Passed", "Status", "Time (ms)", "Memory (kb)", "Integral (ms * kb)"]

            # Build the table rows based on your results
            table = []
            for result in execution_results:
                row = [
                    '🟢' if result['passed'] else '🔴',
                    result['status'],
                    f"{result['time']:.2f}",
                    f"{result['memory']:.2f}",
                    f"{str(result['integral'])}"
                ]
                table.append(row)

            # Print the formatted table
            print(tabulate(table, headers=headers, tablefmt="fancy_outline"))


    def run_evaluation(self):
        pass

if __name__ == "__main__":
    venus_test = VenusLitmusTest(lang="python3", number_of_workers=16, case_multiply=64, max_test_packs=512, monolith_timeout=90)
    venus_test.run_distribution()
    
    
    