Class Demo.Operations.PDF.PDFRequest Extends (%Persistent, Ens.Request)
{

Property KeyIndex As %Integer [ InitialExpression = 1 ];

Storage Default
{
<Data name="PDFRequestDefaultData">
<Value name="1">
<Value>%%CLASSNAME</Value>
</Value>
<Value name="2">
<Value>KeyIndex</Value>
</Value>
</Data>
<DataLocation>^Demo.Operations98A3.PDFRequestD</DataLocation>
<DefaultData>PDFRequestDefaultData</DefaultData>
<ExtentSize>2</ExtentSize>
<IdLocation>^Demo.Operations98A3.PDFRequestD</IdLocation>
<IndexLocation>^Demo.Operations98A3.PDFRequestI</IndexLocation>
<Property name="%%CLASSNAME">
<AverageFieldSize>2</AverageFieldSize>
<OutlierSelectivity>.999999:</OutlierSelectivity>
<Selectivity>0.0001%</Selectivity>
</Property>
<Property name="%%ID">
<AverageFieldSize>3</AverageFieldSize>
<Selectivity>1</Selectivity>
</Property>
<Property name="KeyIndex">
<AverageFieldSize>3</AverageFieldSize>
<Selectivity>50.0000%</Selectivity>
</Property>
<SQLMap name="IDKEY">
<BlockCount>-4</BlockCount>
</SQLMap>
<StreamLocation>^Demo.Operations98A3.PDFRequestS</StreamLocation>
<Type>%Storage.Persistent</Type>
}

}
