#!/bin/bash



DIST_FILE=/dev/stdout
PARSE_LEADING_COMMA=1



usage="$(basename "$0") [-h] FILE_PATH -- program to convert dcgm reports to JSON format \n


    -h  show this help text \n"


parse(){
    nla="\n\t\t"
    close="0"
    text=""
    if ! [[ $1 =~ ^.*\/'dcgm-gpu-stats'.*$ ]]; then
        echo "Skipping file $1, not a dcgm-gpu-stats file"
        return
    fi
    gpu_name=$(echo $1 | 
        awk -F '/' '{
        key="gpu_name"; value=$NF;
        gsub(/dcgm-gpu-stats-/, "", value);
        gsub(/-[0-9]+\.out$/, "", value);
        print value;
        }')
    while IFS= read -r line
    do
        if [[ $line =~ ^'Successfully retrieved statistics for job:'.*$ ]]; then
            job_id=$(echo $line | \
            awk -F ':' '{
            key="job_i"; value=$2
            gsub(/^ |\.$/,"",value)
            print value;
            }')
            continue
        fi


        if [[ $line =~ ^\|' GPU ID:'.*\|$ ]]; then
            gpu_id=$(echo $line | \
            awk -F ':' '{
            key="job_i"; value=$2
            gsub(/^ |\s|\|$/,"",value)
            print value;
            }')
            prefix=""
            if [[ "$PARSE_LEADING_COMMA" == "1" ]]; then
                prefix="," 
            fi
            text="${text}\n\t${prefix}{${nla}\"job_id\":${job_id},${nla}\"gpu_name\": \"${gpu_name}\",${nla}\"gpu_id\": \"${gpu_id}\","
            PARSE_LEADING_COMMA=1
            continue
        fi


        if [[ $line =~ ^\|.*'Avg:'.*'Max:'.*'Min:'.*$ ]]; then
            entry=$(echo $line | \
                awk -F'|' '{ 
                key=$2; value=$3; 
                gsub(/^[ \t-]+|[ \t]+| Due to -$/, "", key); 
                gsub(/^[ \t]+|[ \t]+|+$/, "", value);
                gsub(/Avg/, "\"Avg\"", value);
                gsub(/Max/, "\"Max\"", value);
                gsub(/Min/, "\"Min\"", value);
                gsub("N/A", "\"N/A\"", value);
                gsub(/\.\.\./, "", value);
                print "\"" key "\": {" value "}";
                }')
            text="${text}${nla}${entry},"
            continue
        fi

        if [[ $line =~ ^.*'-  Slowdown Stats  -'.*$ ]]; then
            text="${text}${nla}\"Slowdown Stats\":{"
            nla="\n\t\t\t"
            continue
        fi

        if [[ $line =~ ^.*'Sync Boost'.*$ ]]; then
            entry=$(echo $line | \
                awk -F'|' '{ 
                key=$2; value=$3; 
                gsub(/^[ \t-]+|[ \t]+$/, "", key); 
                gsub(/^[ \t]+|[ \t]+$/, "", value); 
                print "\"" key "\": \"" value "\"";
                }')
            text="${text}${nla}${entry}},"
            nla="\n\t\t"
            continue
        fi

        if [[ $line =~ ^.*'-  Compute Process Utilization  -'.*$ ]]; then
            close="1"
            text="${text}${nla}\"Compute Process Utilization\": ["
            continue
        fi

        if [[ $line =~ ^.*'-  Graphics Process Utilization  -'.*$ ]]; then
            if [[ $close -eq 1 ]]; then
                text=$(echo $text | sed '$ s/.$/\n\t],/')
            fi
            text="${text}${nla}\"Graphics Process Utilization\": ["
            close="1"
            continue
        fi


        if [[ $line =~ ^.*'PID'.*$ ]]; then
            nla="\n\t\t\t"
            pid=$(echo $line | \
            awk -F'|' '{ 
                key=pid; value=$3; 
                gsub(/^[ \t]+|[ \t]+$/, "", value);
                print value;
                }')
            
            # text="${text}${nla}\"${pid_prefix}P${pid}\":{"
            text="${text}${nla}{\"pid\": \"${pid}\","
            continue
        fi

        if [[ $line =~ ^.*'Avg Memory Utilization (%)'.*$ ]]; then
            entry=$(echo $line | \
                awk -F'|' '{ 
                key=$2; value=$3; 
                gsub(/^[ \t-]+|[ \t]+$/, "", key); 
                gsub(/^[ \t]+|[ \t]+$/, "", value); 
                print "\"" key "\": \"" value "\"";
                }')
            text="${text}${nla}${entry}},"
            nla="\n\t\t"
            continue
        fi

        if [[ $line =~ ^\|.*\|.*\|$ ]]; then
            entry=$(echo $line | \
                awk -F'|' '{ 
                key=$2; value=$3; 
                gsub(/^[ \t-]+|[ \t]+$/, "", key); 
                gsub(/^.*Due to - Power.*$/, "Power", key);
                gsub(/^[ \t]+|[ \t]+$/, "", value); 
                print "\"" key "\": \"" value "\"";
                }')
            text="${text}${nla}${entry},"
            continue
        fi

        if [[ $line =~ ^.*'-  Overall Health  -'.*$ ]]; then
            if [[ $close -eq 1 ]]; then
                text=$(echo $text | sed '$ s/.$/\n\t],/')
            fi
            close="0"
            continue
        fi

        if [[ $line =~ ^\s*$ ]]; then
            text=$(echo $text | sed '$s/.$/\n\t}/')
        fi

    done < "$1"
    echo -e "$text" >> "$DIST_FILE"
    echo -e "\n]" >> "$DIST_FILE"
}



if [[ -z "$1" ]]; then
    echo "No argument supplied, please see $(basename "$0") -h for help"
    exit -1
fi

if [ "$1" == "-h" ]; then
  echo -e $usage
  exit 0
fi

if [[ -f $1 ]]; then
    if [[ "$DIST_FILE" != "/dev/stdout" ]]; then
        PARSE_LEADING_COMMA=1
        sed -i '$s/^]$//' "$DIST_FILE"
    else
        PARSE_LEADING_COMMA=0
        printf '['
    fi
    parse $1
else
    echo "File $1 does not exist, please provide a valid file path"
    exit -1
fi

