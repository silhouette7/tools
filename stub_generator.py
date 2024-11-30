'''
    Create stub file according to header file
    Known issues:
    1. If there is a function implementation in the header file, this script may treat the "};" at the end of function as the end of a class in mistake
'''

import sys
import getopt
import os
import re
from enum import Enum

DEFAULT_STUB_OUTPUT_FILE_PREFIX = "unittest_stub-"

AVAILABLE_HEADER_FILE_SUFFIX_LIST = [".h", ".hxx"]

COMMON_INCLUDE_FILES = ["stub.h"]

STUB_FUNC_PREFIX = "stub_"

HEADER_FILE_START_TEMPLATE = (
    "#ifndef HEADER_MARCO\n"
    "#define HEADER_MARCO\n\n"
)

HEADER_FILE_END_TEMPLATE = (
    "\n#endif"
)

PRE_LINE_PENDING = "    "

class ParseState(Enum):
    GLOBAL = 1 << 0
    CLASS = 1 << 1
    FUNCTION = 1 << 2

class StubGenerator:
    def __init__(self, input, output_header, output_source):
        self.input_file_name = input
        self.input_file = None
        self.output_header_name = output_header
        self.output_header_file = None
        self.output_source_name = output_source
        self.output_source_file = None
        self.class_name = None
        self.cur_parse_state = 0
        self.cur_func_name = None
        self.cur_func_return = None
        self.cur_func_args = None
        self.namespace_count = 0

    def initializeStubFile(self):
        header_file_marco = "__" + self.output_header_name.rpartition('.')[0].rpartition('\\')[2].rpartition('/')[2].replace('-', '_').upper() + "_H__"
        self.output_header_file.write(HEADER_FILE_START_TEMPLATE.replace("HEADER_MARCO", header_file_marco))

        for file_name in COMMON_INCLUDE_FILES:
            self.output_header_file.write("#include <" + file_name + ">\n")
        self.output_header_file.write("\n")
        
        self.output_source_file.write("#include \"" + self.output_header_name + "\"\n\n")

    def finalizeStubFile(self):
        while(self.namespace_count > 0):
            self.output_header_file.write("}\n")
            self.namespace_count -= 1

        self.output_header_file.write(HEADER_FILE_END_TEMPLATE)

    def enterClass(self):
        self.cur_parse_state |= ParseState.CLASS.value

    def leaveClass(self):
        self.cur_parse_state &= ~ParseState.CLASS.value
        self.class_name = None

    #TODO: generate default parameter
    @staticmethod
    def generateStubArgs(func_args_str):
        if func_args_str is None:
            return ""
        args_str = ""
        args = func_args_str.split(",")
        for arg in args:
            argv = re.search(r"(const\s*)*([^\*&]+)([\s\*&\)]+)(\S*)$", arg.strip())
            if argv is None:
                continue
            arg_name = argv.group(4)
            if arg_name is not None:
                args_str += PRE_LINE_PENDING + "(void)" + arg_name + ";\n"
        return args_str

    def parseFunction(self):
        args_str = self.generateStubArgs(self.cur_func_args)
        if self.class_name is not None:
            function_signature = "{} {}_{}(void* obj, {})".format(self.cur_func_return, STUB_FUNC_PREFIX + self.class_name, self.cur_func_name, self.cur_func_args)
            args_str = PRE_LINE_PENDING + "(void)obj;\n" + args_str
        else:
            function_signature = "{} {}({})".format(self.cur_func_return, STUB_FUNC_PREFIX + self.cur_func_name, self.cur_func_args)

        self.output_source_file.write(function_signature + "\n{\n" + args_str + "}\n\n")
        self.output_header_file.write(function_signature + ";\n\n")

        self.cur_func_name = None
        self.cur_func_return = None
        self.cur_func_args = None
        self.cur_parse_state &= ~ParseState.FUNCTION.value

    def run(self):
        with open(self.input_file_name, 'r') as self.input_file:
            with open(self.output_header_name, 'w') as self.output_header_file:
                with open(self.output_source_name, 'w') as self.output_source_file:
                    self.initializeStubFile()

                    lines = self.input_file.readlines()
                    for line in lines:
                        #parse namespace
                        namespace_line = re.search(r"\s*namespace\s+([\S]+)$", line)
                        if namespace_line is not None:
                            namespace_name =  namespace_line.group(1)
                            self.output_source_file.write("using namespace " + namespace_name + ";\n\n")
                            self.output_header_file.write("namespace " + namespace_name + "\n{\n")
                            self.namespace_count += 1
                            continue

                        #parse class name
                        class_line = re.search(r"\s*class\s+([a-zA-Z]+)([^;]*$)", line)
                        if class_line is not None:
                            self.class_name = class_line.group(1)
                            if "}" not in class_line.group(2):
                                self.enterClass()
                            continue

                        #TODO: treat "};" as the end of class in mistake, even if it just the end of a function implementation
                        #parse function
                        function_line = re.search(r"(\s*virtual\s*)*(\w[\S\s\*&]+)\s+(\w+)\s*\(([^\)]*)(\)\s*;)*", line)
                        if function_line is not None:
                            self.cur_parse_state |= ParseState.FUNCTION.value
                            self.cur_func_return = function_line.group(2)
                            self.cur_func_name = function_line.group(3)
                            self.cur_func_args = function_line.group(4)
                            function_end = function_line.group(5)
                            if function_end is not None:
                                self.parseFunction()
                            if (self.cur_parse_state & ParseState.CLASS.value) and "};" in line:
                                self.leaveClass()
                            continue

                        #parse function args
                        if self.cur_parse_state & ParseState.FUNCTION.value:
                            args_line = re.search(r"([^\)]*)\s*(\)\s*;)*", line)
                            if args_line is not None:
                                args = args_line.group(1).strip()
                                args_end = args_line.group(2)
                                if args is not None:
                                    self.cur_func_args += args
                                if args_end is not None and self.checkAccessControl() == True:
                                    self.parseFunction()
                            if (self.cur_parse_state & ParseState.CLASS.value) and "};" in line:
                                self.leaveClass()
                            continue

                        #level class
                        if (self.cur_parse_state & ParseState.CLASS.value) and "};" in line:
                            self.leaveClass()
                            continue

                    self.finalizeStubFile()

def checkHeadFile(input):
    if os.path.exists(input) == False:
        return False
    for suffix in AVAILABLE_HEADER_FILE_SUFFIX_LIST:
        if input.endswith(suffix) == True:
            return True
    return False

def generateGtest(input, output_header, output_source):
    generator = StubGenerator(input, output_header, output_source)
    generator.run()
    return

def main(argv):
    try:
        opts, args = getopt.getopt(argv, "hi:o")
    except getopt.GetoptError:
        print("usage -i <input_file> -o <output_file_name_without_suffix>")
        sys.exit(2)

    input = None
    output = None

    for opt, arg in opts:
        if opt == "-h":
            print("usage -i <input_file> -o <output_file_name_without_suffix>")
            sys.exit
        elif opt == "-i":
            input = arg
        elif opt == "-o":
            output = arg
    
    if input is None or checkHeadFile(input) == False:
        print("invalid input")
        sys.exit(2)
    
    if output is None:
        output_header = DEFAULT_STUB_OUTPUT_FILE_PREFIX + input.rpartition(".")[0].rpartition("/")[2].rpartition("\\")[2] + ".h"
        output_source = DEFAULT_STUB_OUTPUT_FILE_PREFIX + input.rpartition(".")[0].rpartition("/")[2].rpartition("\\")[2] + ".cpp"
    else:
        output_header = output + ".h"
        output_source = output + ".cpp"
    
    print("input: {}, output header: {}, output source: {}".format(input, output_header, output_source))
    generateGtest(input, output_header, output_source)

if __name__ == "__main__":
    main(sys.argv[1:])