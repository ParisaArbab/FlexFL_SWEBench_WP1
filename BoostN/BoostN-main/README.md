# README
- modified from BoostNSift.BoostNSift, remove its Sift component
- bug_report is copied from the replication package of LIBRO(https://github.com/coinse/libro), only the bug report of Time-25 is provided in `bug_report`

## Run
1. Required : Set root path in project.settings
2. Required : Set the path to Defects4J in the first line of function `public static void setParameters(String rootDirectory)` in file `src/main/java/configuration/ConfigurationParameters.java` and compile 
```bash
mvn clean install
```
3. Optional : Edit bug_list.txt for bugs to run(Time-25 by default), update bug reports from LIBRO(https://github.com/coinse/libro) and get flattened_bug_report via the following instructions.
```bash
cd scripts
python tools.py
```
4. Required : Get irfl results using BoostN
```bash
bash irfl.sh
```
- The result can be found in `results/Time-25_method-susps.csv`