import os
from csv import DictReader, DictWriter

with open('./bug_list.txt') as f:
    bugs = [e.strip() for e in f.readlines()]

flag = True
for bug in bugs:
        stat_rank = []
        with open(f"../buggy_program/methods_buggy_Defects4j/{bug}.corpusMappingMethodLevelGranularity") as f:
            methods = [e.strip() for e in f.readlines()]
        with open(f"./SBIR/FaultLocalization/data/SBIR_results/sbir_seed{seed}/{bug.split('-')[0].lower()}/{bug.split('-')[1]}/stmt-susps.txt") as f:
            reader = DictReader(f)
            for row in reader:
                file, line = row['Statement'].split('#')
                flag = True
                for method in methods:
                    startline = int(method.split('.')[-2])
                    endline = int(method.split('.')[-1])
                    function = '.'.join(method.split('.')[:-2])
                    class_name = function[:function.find('(')]
                    class_name = class_name[:class_name.rfind('.')]
                    if class_name == file and startline <= int(line) <= endline:
                        stat_rank.append({
                            "File" : class_name,
                            "Signature" : function[len(class_name)+1:],
                            "StartLine" : startline,
                            "EndLine" : endline
                        })
                        flag = False

        rank = []
        for method in stat_rank:
            if method not in rank:
                rank.append(method)
        if len(rank) < 20:
            print(bug, len(rank))
        with open(f'./SBIR_results/{bug}_method-susps.csv', 'w') as f:
            writer = DictWriter(f, fieldnames=rank[0].keys())
            writer.writeheader()
            for row in rank:
                writer.writerow(row)