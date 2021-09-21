import os
def loadfile(file_name,namespace):

    command = "sed -i 's/NAMESPACE/{1}/' {0}".format(file_name,namespace)
    #print(command)
    os.system(command)

    with open(file_name, 'r') as f:
        data = f.read()
        f.close()
        return data

