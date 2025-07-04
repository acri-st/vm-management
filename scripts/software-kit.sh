#!/bin/bash

(
    # Prevent abrupt session closures inside the subshell
    set -e

    API_ENDPOINT=https://sandbox.desp-aas.acri-st.fr
    ANSIBLE_FILE="/tmp/software-kit.yaml"
    VM_ID_FILE="vm.id"
    EXIT_CODE=0

    # Function to get the username (same logic for both)
    get_username() {
        local username=""
        username=$(last -w | grep "logged in" | awk '{print $1}' | grep -v '^root$' | head -n 1)
        
        if [ -z "$username" ]; then
            username=$(logname 2>/dev/null | grep -v '^root$')
        fi

        if [ -z "$username" ] && [ "$USER" != "root" ] && [ -n "$USER" ]; then
            username=$USER
        fi

        if [ -z "$username" ]; then
            error "No valid username found (non-root)." 1
            return 1
        fi

        echo "$username"
    }

    # Dynamically set the log file to include the username
    USERNAME=$(get_username)
    LOG_FILE="/tmp/desp_${USERNAME}.log"
    
    echo "----" > $LOG_FILE

    # Trap errors and log them
    trap "{
        echo \"Script exited with error code: $EXIT_CODE\" >> $LOG_FILE;
    }" EXIT

    # Function to log debug messages
    debug() {
        if [ -n "$DEBUG" ]; then
            dt=$(date '+%Y-%m-%d %H:%M:%S')
            echo "$dt [DEBUG] $1" >> "$LOG_FILE"
        fi
    }

    # Function to log info messages
    info() {
        dt=$(date '+%Y-%m-%d %H:%M:%S')
        echo "$dt [INFO] $1" | tee -a "$LOG_FILE"
    }

    # Function to log error messages
    error() {
        dt=$(date '+%Y-%m-%d %H:%M:%S')
        echo "$dt [ERROR] $1" | tee -a "$LOG_FILE"
        EXIT_CODE=$2
    }

    # Function to get nb processor
    get_nb_processor() {
        nproc
    }

    # Function to fetch Total Memory Information
    get_memory() {
        awk '/MemTotal/ {printf "%.0f GB\n", $2/1000/1000}' /proc/meminfo
    }

    # Function to fetch Bandwidth Information (Highest Speed Interface)
    get_bandwidth() {
        interfaces=$(ls /sys/class/net | grep -vE 'lo|docker|br-|veth')
        for iface in $interfaces; do
            speed=$(cat /sys/class/net/$iface/speed 2>/dev/null)
            if [[ $speed =~ ^[0-9]+$ ]]; then
                echo "${speed}Mb/s"
                return
            fi
        done
        echo "Unknown speed"
    }

    # Function to fetch Total Storage Information
    get_storage() {
        df -h | grep '/$' | awk '$NF == "/" {print $2}'
    }

    # Function to fetch OS Information
    get_os() {
        grep '^PRETTY_NAME=' /etc/os-release | awk -F '=' '{print $2}' | sed 's/"//g'
    }

    # Function to call the API and get the identifier
    get_identifier() {
        local username=$(get_username)  # Reuse the get_username function to get the username
        local processor_nb=$(get_nb_processor)
        local memory=$(get_memory)
        local bandwidth=$(get_bandwidth)
        local storage=$(get_storage)
        local os=$(get_os)

        local payload=$(cat <<EOF
{
    "username": "$username",
    "node_info": {
        "processor_nb": "$processor_nb",
        "memory": "$memory",
        "bandwidth": "$bandwidth",
        "storage": "$storage",
        "os": "$os"
    }
}
EOF
        )
        debug "VM characteristics: $payload" 
        local response=$(curl -s -X POST ${API_ENDPOINT}/api/vm-management/identify \
            -H "Content-Type: application/json" \
            -d "$payload")

        local json_response=$response

        debug "Response from create_identifier API: $json_response"
        if echo "$json_response" | jq -e '.error' > /dev/null 2>&1; then
            local error_message=$(echo "$json_response" | jq -r '.error')
            error "Error getting identifier with response: $error_message" 1
            return 1
        fi
        debug "Identifier payload $json_response"
        local identifier=$(echo "$json_response" | jq -r '.data.vm_id')
        debug "VM identifier: $identifier"
        echo "$identifier" > $VM_ID_FILE 
        echo $identifier
    }

    # Function to get the context using the identifier
    get_context() {
        local identifier=$1

        debug "Sending GET request to context API with identifier: $identifier"

        local response=$(curl -s ${API_ENDPOINT}/api/vm-management/context/$identifier)

        local json_response=$response

        debug "Response from context API: $response"

        if echo "$json_response" | jq -e '.error' > /dev/null 2>&1; then
            local error_message=$(echo "$json_response" | jq -r '.error')
            error "Error getting context with response: $error_message" 1
            return 1
        fi

        local context=$(echo -n "$response" | jq -r '.data')

        script=$(echo -n "$response" | jq -r '.data.content')

        debug "Ansible script from context JSON: $script"

        echo "$script" > $ANSIBLE_FILE
        echo $context 
    }

    # Function to compare the SHA values
    compare_sha() {
        local context_json=$1
        local sha=$(echo "$context_json" | jq -r '.sha')

        debug "SHA from context JSON: $sha"

        local ansible_output_sha=$(sha256sum $ANSIBLE_FILE | awk '{ print $1 }')

        debug "SHA of ansible script output: $ansible_output_sha"

        if [ "$sha" == "$ansible_output_sha" ]; then
            info "SHA values match."
        else
            error "SHA values do not match." 2
            return 2
        fi
    }

    # Main script
    main() {
        info "Starting VM management script"
        debug ">>> Script in debug mode logs in $LOG_FILE <<<"
        if [ -f "$VM_ID_FILE" ]; then
           identifier=$(<"$VM_ID_FILE")
           debug "Identifier found in $VM_ID_FILE:$identifier" 
        else
            local identifier=$(get_identifier) || return 1
        fi
        info "VM Identifier: $identifier"

        local context_json=$(get_context "$identifier") || return 1

        compare_sha "$context_json" || return 2

        /bin/su -c "ANSIBLE_LOCALHOST_WARNING=false ansible-playbook $ANSIBLE_FILE" - ansible | tee -a "$LOG_FILE" || error "Ansible playbook execution failed." 3

        info "VM management script completed"

        notify-send "VM installation completed"
    }

    # Run the main function
    main || error "An error occurred during execution." $?
)
