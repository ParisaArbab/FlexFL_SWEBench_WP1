cat ./bug_list.txt | while read bug
do
    mvn exec:java -Dexec.mainClass="Main" -Dexec.args="$bug"
    mv ./file_docs/$bug/method-susps.csv ./results/${bug}_method-susps.csv
done
