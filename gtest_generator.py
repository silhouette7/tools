'''
    Create gtest unittest file according to header file
    Known issues:
    1. If there is a function implementation in the header file, this script may treat the "};" at the end of function as the end of a class in mistake
    2. Cannot construct class that has not public constructer correctly, e.g. singlton
    3. Cannot analysis default parameter ('=' in the args list)
    4. fail to analysis nested namespace
'''

import sys
import getopt
import os
import re
from enum import Enum

DEFAULT_TEST_OUTPUT_FILE_PREFIX = "test_"

AVAILABLE_HEADER_FILE_SUFFIX_LIST = [".h"]

COMMON_INCLUDE_FILES = ["stub.h",
                        "gtest/gtest.h",
                        "gmock/gmock.h"]

TEST_SUITE_TEMPLATE = (
    "class Template : public ::testing::Test\n"
    "{\n"
    "    virtual void SetUp() override\n"
    "    {\n"
    "        Test::SetUp();\n"
    "    }\n"
    "    virtual void TearDown() override\n"
    "    {\n"
    "        Test::TearDown();\n"
    "    }\n"
    "    static void SetUpTestCase()\n"
    "    {\n"
    "    }\n"
    "    static void TearDownTestCase()\n"
    "    {\n"
    "    }\n"
    "};\n"
)

TEST_FUNC_TEMPLATE = (
    "\nTEST_F(Template_Test_Suite, Template_Test_Func)\n"
    "{\n"
    "Template_args"
    "Template_construct"
    "Template_Test"
    "}\n"
)

PRE_LINE_PENDING = "    "

class ParseState(Enum):
    GLOBAL = 1 << 0
    CLASS = 1 << 1
    CLASS_WITHOUT_CONSTRUCTER = 1 << 2
    CONSTRUCTER = 1 << 3
    FUNCTION = 1 << 4

class ClassAccessControl(Enum):
    PRIVATE = 1
    PUBLIC = 2

class GtestGenerator:
    def __init__(self, input, output, access_control):
        self.input_file_name = input
        self.input_file = None
        self.output_file_name = output
        self.output_file = None
        self.access_control = access_control
        self.class_name = None
        self.class_construct_args = None
        self.class_consturct_str = None
        self.test_suite_name = None
        self.cur_access_state = None
        self.cur_parse_state = 0
        self.cur_func_name = None
        self.cur_func_args = None
        self.include = ""
        self.namespace = ""
        self.test_suite = ""
        self.test_case = ""

    def initializeGtestFile(self):
        for file_name in COMMON_INCLUDE_FILES:
            self.include += ("#include <" + file_name + ">\n")

        self.include += ("#include \"" + self.input_file_name.rpartition("/")[2].rpartition("\\")[2] + "\"\n")
        self.namespace += "using namespace ::testing;\n"
        self.test_suite += TEST_SUITE_TEMPLATE.replace("Template", self.test_suite_name)

    def finalizeGtestFile(self):
        self.output_file.write(self.include + "\n")
        self.output_file.write(self.namespace + "\n")
        self.output_file.write(self.test_suite + "\n")
        self.output_file.write(self.test_case)

    def checkAccessControl(self):
        return self.access_control != True or (not self.cur_parse_state & ParseState.CLASS.value) or self.cur_access_state == ClassAccessControl.PUBLIC

    def enterClass(self):
        self.class_consturct_str = PRE_LINE_PENDING + self.class_name + " testInstance;\n"
        self.cur_access_state = ClassAccessControl.PRIVATE
        self.cur_parse_state |= ParseState.CLASS.value
        self.cur_parse_state |= ParseState.CLASS_WITHOUT_CONSTRUCTER.value

    def leaveClass(self):
        self.cur_access_state = None
        self.cur_parse_state &= ~ParseState.CLASS.value
        self.cur_parse_state &= ~ParseState.CLASS_WITHOUT_CONSTRUCTER.value
        self.class_name = None
        self.class_construct_args = None
        self.class_consturct_str = None

    #TODO: generate default parameter
    @staticmethod
    def generateTestArgs(func_args_str, arg_prefix):
        if func_args_str is None:
            return [["", ""]]
        i = 0
        args_cons_str = ""
        args_str = ""
        args = func_args_str.split(",")
        for arg in args:
            argv = re.search(r"(const\s*)*([^\*&]+)([\s\*&\)]+)\S*$", arg.strip())
            if argv is None:
                continue
            arg_type = argv.group(2).strip()
            pointer_or_ref = argv.group(3).strip()
            if arg_type == "void" and (pointer_or_ref is None or pointer_or_ref == ""):
                continue
            if pointer_or_ref is not None and pointer_or_ref == "*":
                args_cons_str += PRE_LINE_PENDING + "{}* {}{} = nullptr;\n".format(arg_type, arg_prefix, str(i))
            else:
                args_cons_str += PRE_LINE_PENDING + "{} {}{};\n".format(arg_type, arg_prefix, str(i))
            args_str += arg_prefix + str(i) + ", "
            i += 1
        args_str = args_str.rstrip(", ")
        return [[args_cons_str, args_str]]

    def parseConstructer(self):
        if self.cur_parse_state & ParseState.CLASS_WITHOUT_CONSTRUCTER.value:
            args_str_list = self.generateTestArgs(self.class_construct_args, "construct_arg")
            args_cons_str, args_str = args_str_list[0]
            self.class_consturct_str = args_cons_str
            self.class_consturct_str += PRE_LINE_PENDING + self.class_name + " testInstance{" + args_str + "};\n"
        self.cur_parse_state &= ~ParseState.CONSTRUCTER.value
        self.cur_parse_state &= ~ParseState.CLASS_WITHOUT_CONSTRUCTER.value

    def parseFunction(self):
        #parse arguments
        i = 0
        args_str_list = self.generateTestArgs(self.cur_func_args, "arg")
        for args_cons_str, args_str in args_str_list:
            result = TEST_FUNC_TEMPLATE.replace("Template_Test_Suite", self.test_suite_name).replace("Template_Test_Func", self.cur_func_name + str(i)).replace("Template_args", args_cons_str)
            if self.cur_parse_state & ParseState.CLASS.value:
                result = result.replace("Template_construct", self.class_consturct_str).replace("Template_Test", PRE_LINE_PENDING + "testInstance.{}({});\n".format(self.cur_func_name, args_str))
            else:
                result = result.replace("Template_construct", "").replace("Template_Test", PRE_LINE_PENDING + "{}({});\n".format(self.cur_func_name, args_str))
            self.test_case += result
            i += 1

        self.cur_func_name = None
        self.cur_func_args = None
        self.cur_parse_state &= ~ParseState.FUNCTION.value

    def run(self):
        with open(self.input_file_name, 'r') as self.input_file:
            with open(self.output_file_name, 'w') as self.output_file:
                self.test_suite_name = re.search(r"(\w+).\w+", self.input_file_name.rpartition("/")[2].rpartition("\\")[2]).group(1) + "Test"
                self.initializeGtestFile()

                lines = self.input_file.readlines()
                for line in lines:
                    #annotation
                    if line.strip().startswith("//"):
                        continue

                    #parse namespace
                    namespace_line = re.search(r"\s*namespace\s+([\S]+)$", line)
                    if namespace_line is not None:
                        self.namespace += ("using namespace " + namespace_line.group(1) + ";\n")
                        continue

                    #parse class name
                    class_line = re.search(r"\s*class\s+([a-zA-Z]+)([^;]*$)", line)
                    if class_line is not None:
                        self.class_name = class_line.group(1)
                        if "}" not in class_line.group(2):
                            self.enterClass()
                        continue

                    #parse constructer (only call the first constructer if there are more than one)
                    if self.cur_parse_state & ParseState.CLASS.value:
                        constructer_line = re.search(r"\s*[^~]" + self.class_name + r"\s*\(([^\)]*)(\)\s*;)*", line)
                        if constructer_line is not None:
                            self.cur_parse_state |= ParseState.CONSTRUCTER.value
                            self.class_construct_args = constructer_line.group(1)
                            constructer_end = constructer_line.group(2)
                            if constructer_end is not None:
                                self.parseConstructer()
                            continue

                    #parse constructer args
                    if self.cur_parse_state & ParseState.CONSTRUCTER.value:
                        args_line = re.search(r"([^\)]*)\s*(\)\s*;)*", line)
                        if args_line is not None:
                            args = args_line.group(1).strip()
                            args_end = args_line.group(2)
                            if args is not None:
                                self.class_construct_args += args
                            if args_end is not None:
                                self.parseConstructer()
                            continue

                    #TODO: treat "};" as the end of class in mistake, even if it just the end of a function implementation
                    #parse function
                    function_line = re.search(r"[\w\s]*(\w[\w\s\*&]+)\s+(\w+)\s*\(([^\)]*)(\)\s*;)*", line)
                    if function_line is not None:
                        self.cur_parse_state |= ParseState.FUNCTION.value
                        self.cur_func_name = function_line.group(2)
                        self.cur_func_args = function_line.group(3)
                        function_end = function_line.group(4)
                        if function_end is not None:
                            if self.checkAccessControl() == True:
                                self.parseFunction()
                            else:
                                self.cur_func_name = None
                                self.cur_func_args = None
                                self.cur_parse_state &= ~ParseState.FUNCTION.value
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

                    #parse access control
                    access_control_line = re.search(r"\s*(public:|private:|protected:)\s*", line)
                    if access_control_line is not None:
                        if "public:" == access_control_line.group(1):
                            self.cur_access_state = ClassAccessControl.PUBLIC
                        else:
                            self.cur_access_state = ClassAccessControl.PRIVATE
                        continue

                    #level class
                    if (self.cur_parse_state & ParseState.CLASS.value) and "};" in line:
                        self.leaveClass()
                        continue

                self.finalizeGtestFile()

def checkHeadFile(input):
    if os.path.exists(input) == False:
        return False
    for suffix in AVAILABLE_HEADER_FILE_SUFFIX_LIST:
        if input.endswith(suffix) == True:
            return True
    return False

def generateGtest(input, output, access_control):
    generator = GtestGenerator(input, output, access_control)
    generator.run()

def main(argv):
    try:
        opts, args = getopt.getopt(argv, "hi:o", ["no-access-control"])
    except getopt.GetoptError:
        print("usage -i <input_file> -o <output_file>")
        sys.exit(2)

    input = None
    output = None
    access_control = True

    for opt, arg in opts:
        if opt == "-h":
            print("usage -i <input_file> -o <output_file>")
            sys.exit()
        elif opt == "-i":
            input = arg
        elif opt == "-o":
            output = arg
        elif opt == "--no-access-control":
            access_control = False
    
    if input is None or checkHeadFile(input) == False:
        print("invalid input")
        sys.exit(2)
    
    if output is None:
        output = DEFAULT_TEST_OUTPUT_FILE_PREFIX + input.rpartition(".")[0].rpartition("/")[2].rpartition("\\")[2] + ".cpp"
    
    print("input: {}, output: {}".format(input, output))
    generateGtest(input, output, access_control)

if __name__ == "__main__":
    main(sys.argv[1:])