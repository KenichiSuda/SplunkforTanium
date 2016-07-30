#!/usr/bin/python
###############################################################################
#
#
###############################################################################

import os
import re
import sys
import ssl
import httplib
import argparse
import HTMLParser
import splunk.entity as entity
import splunk.clilib.cli_common as spcli


class TaniumQuestion:
    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password
        self.path = os.path.dirname(os.path.realpath(__file__))
        self.path = self.path.replace('\\', '/')

        with open(self.path + '/xml/submit_nlp_template.xml') as x:
            self.SUBMIT_NLP_TEMPLATE = x.read()

    def check_xml_error(self, xml_text):
        """
        NOTE: Do no use this error check on the final results xml.
        The keyword 'ERROR' may be a valid sensor response!
        TODO: Fix the problem in the NOTE!
        """

        if re.search('ERROR', xml_text) != None:
            sys.stderr.write("THERE WAS AN ERROR PROCESSING THE XML REQUEST")
            sys.stderr.write(xml_text)
            print "ERROR,ERROR,ERROR"
            print "There was an error processing the xml request," + \
                  "Please run the script on the command line and check" + \
                  str(xml_text).replace(',', '_')
            sys.exit(0)

    def make_soap_connection(self, soap_message):
        """
        TODO: wrap this in a try/except
        """

        webservice = httplib.HTTPSConnection(self.host, context=ssl._create_unverified_context())
        webservice.putrequest("POST", "/soap")
        webservice.putheader("Host", self.host)
        webservice.putheader("User-Agent", "Python post")
        webservice.putheader("Content-type", "text/xml; charset=\"UTF-8\"")
        webservice.putheader("Content-length", "%d" % len(soap_message))
        webservice.putheader("SOAPAction", "\"\"")
        webservice.endheaders()
        webservice.send(soap_message)

        res = webservice.getresponse()
        # print res.status, res.reason
        data = res.read()
        webservice.close()
        return data

    def send_request_to_tanium(self, question):
        """
        This function kicks off a request to a Tanium server. The request is an
        unfiltered call to a particular sensor. Since the sensor request is
        unfiltered the sensor will run on all hosts that the Tanium server is
        supporting.
        """
        parse_list = []
        best_regex = '(\<parse_result_groups\>)(.*?)(\<\/parse_result_group\>)'
        id_ext_regex = '(\<result_object\>\<question\>\<id\>)(.*?)(\<\/id\>)'
        verbage_regex = '(\<question_text\>)(.*?)(\<\/question_text\>)'

        # ------------- parse question, get best guess ------
        soap_message = self.SUBMIT_NLP_TEMPLATE % (self.username, self.password, \
                                                   question)

        guess_xml = self.make_soap_connection(soap_message)
        self.check_xml_error(guess_xml)

        for element in re.finditer(verbage_regex, guess_xml, re.DOTALL):
            element = str(element.group(2))
            element = str(HTMLParser.HTMLParser().unescape(element))
            parse_list.append(element)

        parse_list.pop(0)
        return parse_list

    def ask_tanium_a_question(self, question):

        parse_list = self.send_request_to_tanium(question)
        return parse_list


def getCredentials(sessionKey):
    myapp = 'tanium'
    try:
        # list all credentials
        entities = entity.getEntities(['admin', 'passwords'], namespace=myapp,
                                      owner='nobody', sessionKey=sessionKey)
    except Exception, e:
        raise Exception("Could not get %s credentials from splunk. Error: %s" % (myapp, str(e)))

        # return first set of credentials

    for i, c in entities.items():
        username = c['username']
    password = c['clear_password']
    # return c['username'], c['clear_password']
    # TAB causes a funky separator
    password = password.split("splunk_cred_sep``", 1)[1]
    return username, password
    raise Exception("No credentials have been found")


def get_input_config():
    sessionXml = sys.stdin.readline()

    if len(sessionXml) == 0:
        sys.stderr.write("Did not receive a session key from splunkd. " +
                         "Please enable passAuth in inputs.conf for this " +
                         "script\n")
        exit(2)

    # parse the xml sessionKey

    start = sessionXml.find('<authToken>') + 11
    stop = sessionXml.find('</authToken>')
    authTok = sessionXml[start:stop]

    username, password = getCredentials(authTok)
    return username, password



# ------------------------------MAIN MODULE--------------------------------------
def main():
    # sys.stderr = open('err.txt', 'w+')
    # Redirect error to out, so we can see any errors
    sessionXml = sys.stdin.readline()

    if len(sessionXml) == 0:
       sys.stderr.write("Did not receive a session key from splunkd. " +
                        "Please enable passAuth in inputs.conf for this " +
                        "script\n")
       exit(2)

    #parse the xml sessionKey

    start = sessionXml.find('<authToken>') + 11
    stop = sessionXml.find('</authToken>')
    authTok = sessionXml[start:stop]


    # now get tanium credentials - might exit if no creds are available
    username, passwd = getCredentials(authTok)

    sys.stderr = sys.stdout

    configuration_dict = spcli.getConfStanza('tanium_customized', 'taniumhost')

    tanium_server = configuration_dict['content']


    parser = argparse.ArgumentParser(description='Tanium Splunk NLP Parser')
    """
    parser.add_argument(
            '--tanium',
            metavar='TANIUM',
            required=True,
            help='Tanium server')

    parser.add_argument(
            '--user',
            metavar='USER',
            required=True,
            help='user name')

    parser.add_argument(
            '--password',
            metavar='PASSWORD',
            required=True,
            help='user password')
    """

    parser.add_argument(
            '--question',
            metavar='QUESTION',
            required=True,
            help='nlp question')

    args = vars(parser.parse_args())

    tanium = tanium_server
    user = username
    password = passwd
    question = args['question']

    # end processing args now inst the Tanium class
    my_tanium = TaniumQuestion(tanium, user, password)

    # send the question to Tanium
    response = my_tanium.ask_tanium_a_question(question)

    print "Possible Parsed Translations"

    for element in response:
        print element


# ----------------------------MAIN ENTRY POINT-----------------------------------

if __name__ == '__main__':
    main()
