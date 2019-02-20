#!/usr/bin/env python3
#
# Copyright (c) 2019 Ableton AG, Berlin. All rights reserved.
#
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file.

"""A small wrapper script to call CodeNarc and interpret its output."""

import argparse
import os
import platform
import subprocess
import sys
import xmltodict


DEFAULT_REPORT_FILE = 'codenarc-report.xml'


def _guess_groovy_home():
    """Try to determine the location where Groovy is installed.

    :return: Path of the Groovy installation, or None if it can't be determined.
    """
    if 'GROOVY_HOME' in os.environ:
        return os.environ['GROOVY_HOME']

    if platform.system() == 'Darwin':
        brew_groovy_home = '/usr/local/opt/groovysdk/libexec'
        if os.path.exists(brew_groovy_home):
            return brew_groovy_home

    return None


def _print_violations(package_file_path, violations):
    """Print violations for a file.

    :param package_file_path: File path.
    :param violations: List of Violation elements.
    :return: Number of violations for the file.
    """
    for violation in violations:
        violation_message = f'{violation["@ruleName"]}: {violation["Message"]}'
        print(f'{package_file_path}:{violation["@lineNumber"]}: {violation_message}')

    return len(violations)


def _print_violations_in_files(package_path, files):
    """Print violations for each file in a package.

    :param package_path: Package path.
    :param files: List of File elements.
    :return: Number of violations for all files in the package.
    """
    num_violations = 0

    for package_file in files:
        num_violations += _print_violations(
            f'{package_path}/{package_file["@name"]}',
            _safe_list_wrapper(package_file["Violation"]),
        )

    return num_violations


def _print_violations_in_packages(packages):
    """Print violations for each package in a list of packages.

    :param packages: List of Package elements.
    :return: Number of violations for all packages.
    """
    num_violations = 0

    # I believe that CodeNarc has a bug where it erroneously sets filesWithViolations
    # to the same value in every package. Therefore rather than looking at this attribute
    # value, we check to see if there are any File elements in the package.
    for package in [p for p in packages if 'File' in p]:
        # CodeNarc uses the empty string for the top-level package, which we translate to
        # '.', which prevents the violation files from appearing as belonging to '/'.
        package_path = package['@path']
        if not package_path:
            package_path = '.'

        num_violations += _print_violations_in_files(
            package_path,
            _safe_list_wrapper(package['File']),
        )

    return num_violations


def _remove_report_file(report_file):
    if os.path.exists(report_file):
        os.remove(report_file)


def _safe_list_wrapper(element):
    """Wrap an XML element in a list if necessary.

    This function is used to safely handle data from xmltodict. If an XML element has
    multiple children, they will be returned in a list. However, a single child is
    returned as a dict. By wrapping single elements in a list, we can use the same code to
    handle both cases.
    """
    return element if isinstance(element, list) else [element]


def parse_args(args):
    """Parse arguments from the command line."""
    arg_parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    arg_parser.add_argument(
        '--codenarc-version',
        default=os.environ.get('CODENARC_VERSION'),
        help='CodeNarc version to use',
    )

    arg_parser.add_argument(
        '--gmetrics-version',
        default=os.environ.get('GMETRICS_VERSION'),
        help='GMetrics version to use',
    )

    arg_parser.add_argument(
        '--groovy-home',
        default=_guess_groovy_home(),
        help='Groovy home directory',
    )

    arg_parser.add_argument(
        '--home',
        default=os.path.realpath(os.path.dirname(__file__)),
        help='Groovylint home directory',
    )

    arg_parser.add_argument(
        '--slf4j-version',
        default=os.environ.get('SLF4J_VERSION'),
        help='SLF4J version to use',
    )

    arg_parser.add_argument(
        'codenarc_options',
        nargs='*',
        action='append',
        help='All options after "--" will be passed to CodeNarc',
    )

    parsed_args = arg_parser.parse_args(args)

    if not parsed_args.codenarc_version:
        raise ValueError('Could not determine CodeNarc version')
    if not parsed_args.gmetrics_version:
        raise ValueError('Could not determine GMetrics version')
    if not parsed_args.slf4j_version:
        raise ValueError('Could not determine SLF4J version')

    parsed_args.codenarc_options = [
        option for sublist in parsed_args.codenarc_options for option in sublist
    ]

    return parsed_args


def parse_xml_report(xml_text):
    """Parse XML report text generated by CodeNarc.

    :param xml_text: Raw XML text of CodeNarc report.
    :return: 0 on success, 1 if any violations were found
    """
    xml_doc = xmltodict.parse(xml_text)

    package_summary = xml_doc['CodeNarc']['PackageSummary']
    total_files_scanned = package_summary['@totalFiles']
    total_violations = _print_violations_in_packages(
        _safe_list_wrapper(xml_doc['CodeNarc']['Package']),
    )

    print(f'Scanned {total_files_scanned} files')
    if total_violations == 0:
        print('No violations found')
        return 0

    print(f'Found {total_violations} violation(s):')
    _print_violations_in_packages(_safe_list_wrapper(xml_doc['CodeNarc']['Package']))
    return total_violations


def run_codenarc(args, report_file=DEFAULT_REPORT_FILE):
    """Run CodeNarc on specified code.

    :param args: Parsed command line arguments.
    :param report_file: Name of report file to generate.
    :return: Raw XML text report generated by CodeNarc.
    """
    home_dir = args.home
    groovy_home = args.groovy_home
    codenarc_version = args.codenarc_version
    gmetrics_version = args.gmetrics_version
    slf4j_version = args.slf4j_version

    classpath = [
        home_dir,
        f'{groovy_home}/lib/*',
        f'{home_dir}/CodeNarc-{codenarc_version}.jar',
        f'{home_dir}/GMetrics-{gmetrics_version}.jar',
        f'{home_dir}/slf4j-{slf4j_version}/slf4j-api-{slf4j_version}.jar',
        f'{home_dir}/slf4j-{slf4j_version}/slf4j-simple-{slf4j_version}.jar',
    ]

    # -rulesetfiles must not be an absolute path, only a relative one to the CLASSPATH
    codenarc_call = [
        'java',
        '-classpath',
        ':'.join(classpath),
        'org.codenarc.CodeNarc',
        '-rulesetfiles=ruleset.groovy',
        f'-report=xml:{report_file}',
    ] + args.codenarc_options

    output = subprocess.run(
        codenarc_call,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
    )
    sys.stdout.buffer.write(output.stdout)

    # CodeNarc doesn't fail on compilation errors, it just logs a message for each file
    # that could not be compiled and generates a report for everything else. It also does
    # not return a non-zero code in such cases. For our purposes, we want to treat syntax
    # errors (and similar problems) as a failure condition.
    if 'Compilation failed' in str(output.stdout):
        _remove_report_file(report_file)
        raise ValueError('Error when compiling files!')

    if output.returncode != 0:
        _remove_report_file(report_file)
        raise ValueError(f'CodeNarc failed with return code {output.returncode}')
    if not os.path.exists(report_file):
        _remove_report_file(report_file)
        raise ValueError(f'{report_file} was not generated, aborting!')

    with open(report_file) as xml_file:
        xml_text = xml_file.read()
    _remove_report_file(report_file)

    return xml_text


if __name__ == '__main__':
    sys.exit(parse_xml_report(run_codenarc(parse_args(sys.argv[1:]))))
