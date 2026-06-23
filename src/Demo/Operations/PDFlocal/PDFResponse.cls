Class Demo.Operations.PDFlocal.PDFResponse Extends (%Persistent, Ens.Response)
{

Property NextKeyIndex As %Integer;

Property PdfId As %Integer;

Property PdfText As %String(MAXLEN = "");

Storage Default
{
<Data name="PDFResponseDefaultData">
<Value name="1">
<Value>%%CLASSNAME</Value>
</Value>
<Value name="2">
<Value>NextKeyIndex</Value>
</Value>
<Value name="3">
<Value>PdfId</Value>
</Value>
<Value name="4">
<Value>PdfText</Value>
</Value>
</Data>
<DataLocation>^Demo.OperationC7BF.PDFResponseD</DataLocation>
<DefaultData>PDFResponseDefaultData</DefaultData>
<ExtentSize>1</ExtentSize>
<IdLocation>^Demo.OperationC7BF.PDFResponseD</IdLocation>
<IndexLocation>^Demo.OperationC7BF.PDFResponseI</IndexLocation>
<Property name="%%CLASSNAME">
<AverageFieldSize>2</AverageFieldSize>
<OutlierSelectivity>.999999:</OutlierSelectivity>
<Selectivity>0.0001%</Selectivity>
</Property>
<Property name="%%ID">
<AverageFieldSize>3</AverageFieldSize>
<Selectivity>1</Selectivity>
</Property>
<Property name="NextKeyIndex">
<AverageFieldSize>2</AverageFieldSize>
<OutlierSelectivity>.999999:0</OutlierSelectivity>
<Selectivity>0.0001%</Selectivity>
</Property>
<Property name="PdfId">
<AverageFieldSize>3</AverageFieldSize>
<OutlierSelectivity>.999999:3</OutlierSelectivity>
<Selectivity>0.0001%</Selectivity>
</Property>
<Property name="PdfText">
<AverageFieldSize>2</AverageFieldSize>
<OutlierSelectivity>.999999:</OutlierSelectivity>
<Selectivity>0.0001%</Selectivity>
</Property>
<SQLMap name="IDKEY">
<BlockCount>-4</BlockCount>
</SQLMap>
<StreamLocation>^Demo.OperationC7BF.PDFResponseS</StreamLocation>
<Type>%Storage.Persistent</Type>
}

}
