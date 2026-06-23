Class Demo.Service.StartPDFImportServicelocal Extends Ens.BusinessService
{

Parameter ADAPTER = "Ens.InboundAdapter";

Method OnProcessInput(pInput As %RegisteredObject, Output pOutput As %RegisteredObject) As %Status
{
    set tRequest = ##class(Ens.Request).%New()
    set tResponse = ##class(Ens.Response).%New()
    set tSC = ..SendRequestSync("Injection Process Local", tRequest, .tResponse)
    try {
        do ##class(Ens.Director).EnableConfigItem("Start PDF Import local", 0, 1) 
    }
    Catch ex { }


    return $$$OK
}

}
