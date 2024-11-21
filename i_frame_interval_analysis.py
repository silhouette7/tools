import sys
import getopt
import os
import pandas as pd
import matplotlib.pyplot as plt

def caculate_i_frame(frame_info_file, stream_index):
    with open(frame_info_file) as file_object:
        lines = file_object.readlines()

    list_i_frame_interval = []
    previous_time = 0
    cur_time = 0
    i_frame = False
    valid_frame = False

    for line in lines:
        if line.find("stream_index=") != -1:
            cur_index = int(line[13:])
            if cur_index == stream_index:
                valid_frame = True
        elif line.find("pts_time=") != -1:
            cur_time = float(line[9:])
        elif "pict_type=I" in line:
            i_frame = True
        elif "[/FRAME]" in line:
            if i_frame == True and valid_frame == True:
                list_i_frame_interval.append(cur_time - previous_time)
                previous_time = cur_time
            cur_time = 0
            i_frame = False
            valid_frame = False

    return list_i_frame_interval

def list_to_excel(list, excel_file_name):
    df = pd.DataFrame(list)
    df.to_excel(excel_file_name, index=False)

def draw_by_list(list, title, xlabel, ylabel):
    plt.plot(list)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.show()

def main(argv):
    input = None
    output = None
    stream_index = None
    export_plot = False
    export_xlsx = False

    try:
        opts, args = getopt.getopt(argv, "hxpi:s:o:")
    except getopt.GetoptError:
        print("usage: -x (output result to xlsx) -p (output result to plot) -i <inputfile> -s <stream_index> -o <outputfile>")
        sys.exit(2)

    for opt, arg in opts:
        if opt == "-h":
            print("usage: -x (output result to xlsx) -p (output result to plot) -i <inputfile> -s <stream_index> -o <outputfile>")
            print("input file shall be output of ffprobe -i -show_frames")
            sys.exit()
        elif opt == "-x":
            export_xlsx = True
        elif opt == "-p":
            export_plot = True
        elif opt == "-i":
            input = arg
        elif opt == "-s":
            try:
                stream_index = int(arg)
            except ValueError:
                print("stream_index shall be a number")
                sys.exit(2)
        elif opt == "-o":
            output = arg
    
    if input is None or os.path.exists(input) == False or stream_index is None:
        print("invalid input")
        sys.exit(2)

    i_frame_interval_list = caculate_i_frame(input, stream_index)
    print(i_frame_interval_list)

    if export_plot:
        draw_by_list(i_frame_interval_list, "i frame interval", "i frame", "interval")
    
    if export_xlsx:
        if output is None:
            print("invalid output")
            sys.exit(2)
        list_to_excel(i_frame_interval_list, output)

if __name__ == "__main__":
    main(sys.argv[1:])