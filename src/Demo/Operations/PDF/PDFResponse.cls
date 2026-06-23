Class Demo.Operations.PDF.PDFResponse Extends (%Persistent, Ens.Response)
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
<DataLocation>^Demo.Operation98A3.PDFResponseD</DataLocation>
<DefaultData>PDFResponseDefaultData</DefaultData>
<ExtentSize>2</ExtentSize>
<IdLocation>^Demo.Operation98A3.PDFResponseD</IdLocation>
<IndexLocation>^Demo.Operation98A3.PDFResponseI</IndexLocation>
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
<AverageFieldSize>2.5</AverageFieldSize>
<Selectivity>50.0000%</Selectivity>
</Property>
<Property name="PdfId">
<AverageFieldSize>3</AverageFieldSize>
<Selectivity>50.0000%</Selectivity>
</Property>
<Property name="PdfText">
<AverageFieldSize>11066.5</AverageFieldSize>
<Selectivity>50.0000%</Selectivity>
</Property>
<SQLMap name="IDKEY">
<BlockCount>-20</BlockCount>
</SQLMap>
<StreamLocation>^Demo.Operation98A3.PDFResponseS</StreamLocation>
<Type>%Storage.Persistent</Type>
}

}
