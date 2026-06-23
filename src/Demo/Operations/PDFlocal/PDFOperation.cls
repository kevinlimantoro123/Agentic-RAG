Class Demo.Operations.PDFlocal.PDFOperation Extends Ens.BusinessOperation
{

Property DirectoryPath As %String(MAXLEN = "");

Parameter SETTINGS = "DirectoryPath:Local File";

Method OnGetPDFFromLocal(pRequest As Demo.Operations.PDFlocal.PDFRequest, Output pResponse As Demo.Operations.PDFlocal.PDFResponse) As %Status
{

    set tSc = $$$OK

    try {
        // 1st pass: tKeyIndex = 1
        // 2nd pass: tKeyIndex = 2
        set tKeyIndex = pRequest.KeyIndex

        // ..Key = "Abble.pdf,Logystics_Eng.pdf"
        // 1st pass: tKey = "Abble.pdf"
        // 2nd pass: tKey = "Logystics_Eng.pdf"
        set filenamelist = ..getFilenameList(..DirectoryPath,"*pdf")
        $$$TRACE("DirectoryPath:"_..DirectoryPath)
        set tKey = $ZSTRIP($PIECE(filenamelist, ",", tKeyIndex), "<>W")

        $$$TRACE("Key:"_tKey)

        // Extracting out PDF text as %String
        set tPdf = ..GetPDFFromLocal(..DirectoryPath_tKey)

        set tPdfRecord = ##class(Demo.PDFRecord).%New()

        set tPdfRecord.Text = tPdf

        $$$ThrowOnError(tPdfRecord.%Save()) 

        set tPdfId = tPdfRecord.%Id()


        set pResponse = ##class(Demo.Operations.PDFlocal.PDFResponse).%New()

        set pResponse.PdfId = tPdfId

        set pResponse.PdfText = tPdf

        // 1st pass: tNextKey = "Logystics_Eng.pdf"
        // 2nd pass: tNextKey = ""
        set tNextKey = $ZSTRIP($PIECE(filenamelist, ",", tKeyIndex + 1), "<>W")

        if (tNextKey '= "") {
            // 1st pass: NextKeyIndex = 2
            set pResponse.NextKeyIndex = tKeyIndex + 1
        } else {
            // 2nd pass: NextKeyIndex = 0
            set pResponse.NextKeyIndex = 0
        }     
        
    } catch tEx {
        set tSc = tEx.AsStatus()
    }

    return tSc
}

Method getFilenameList(pDir As %String, pMask As %String) As %String
{
   set dir=##class(%File).NormalizeDirectory(pDir)
   set result=##class(%ResultSet).%New("%File:FileSet")
   do result.Execute(dir,pMask)
   set filenamelist = ""
   while result.Next() {
    set filename = ##class(%File).GetFilename(result.GetDataByName("Name"))
    set filenamelist = filenamelist_","_filename
   }
   return $ZSTRIP(filenamelist,"<P")
}

Method GetPDFFromLocal(pKey As %String) As %SYS.Python [ Language = python ]
{
    from io import BytesIO
    from PyPDF2 import PdfReader
    
    if (pKey!=""):
        reader = PdfReader(pKey)
        
        text = ""

        for page in reader.pages:
            text += page.extract_text()

        return text
    else:
        return ""
}

Method GetPDFFromS3(pKey As %String) As %SYS.Python [ Language = python ]
{
    from io import BytesIO
    from PyPDF2 import PdfReader
    import boto3
    from botocore import UNSIGNED
    from botocore.client import Config
    from botocore.exceptions import ClientError

    if(self.Bucket != "" and self.Key != ""):

        # Initialize a session using Amazon S3 with unsigned configuration
        s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))

        response = s3.get_object(Bucket=self.Bucket,Key=pKey)

        reader = PdfReader(BytesIO(response['Body'].read()))

        text = ""

        for page in reader.pages:
            text += page.extract_text()

        return text
    else:
        return ""
}

XData MessageMap
{
<MapItems>
  <MapItem MessageType="Demo.Operations.PDFlocal.PDFRequest">
    <Method>OnGetPDFFromLocal</Method>
  </MapItem>
</MapItems>
}

}
